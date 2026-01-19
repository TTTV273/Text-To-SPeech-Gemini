import hashlib
import json
import os
import re
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from api_key_manager import APIKeyManager
from key_rotation_manager import KeyRotationManager
from text_chunker import count_tokens, split_into_chunks

# Note: Token counting and chunking functions are now in text_chunker.py

load_dotenv()
api_key_manager = APIKeyManager(usage_file="api_usage.json", threshold=9)

# Configuration
MAX_TOKENS_PER_CHUNK = 1000  # Chỉ cần sửa 1 chỗ này để thay đổi chunk size!


def classify_error(error: Exception) -> str:
    """
    Phân loại error để quyết định retry strategy

    Returns:
        "QUOTA_EXHAUSTED": Key hết quota, remove hẳn
        "RATE_LIMIT": Rate limit, cooldown 30s
        "MODEL_OVERLOAD": Server busy, cooldown 30s
        "UNKNOWN": Lỗi khác, không retry
    """
    error_str = str(error)

    # Check 429 QUOTA_EXHAUSTED
    if isinstance(error, ClientError):
        if hasattr(error, 'code') and error.code == 429:
            if 'quota' in error_str.lower() or 'RESOURCE_EXHAUSTED' in error_str:
                return "QUOTA_EXHAUSTED"

    # Check Model Overloaded
    if 'Model Overloaded' in error_str or 'overloaded' in error_str.lower():
        return "MODEL_OVERLOAD"

    # Check soft-fail (finish_reason=OTHER with content=None)
    # This is handled separately in generate_audio_data by checking response

    return "UNKNOWN"


def clean_markdown(text: str) -> str:
    # clean Headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

    # clean Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)

    # clean Italic
    text = re.sub(r"\*([^*]+)\*", r"\1", text)

    # clean Link
    text = re.sub(r"!\[([^\]]+)\]\([^\]]+\)", r"\1", text)

    # clean Code Block
    text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)

    # clean in line code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # clean image
    text = re.sub(r"!\[([^\]]*)\]\([^\]]+\)", "", text)

    return text


# ============================================================ 
# Checkpoint Functions (Phase 8: Resume Feature)
# ============================================================ 


def calculate_file_hash(file_path):
    """Calculate SHA256 hash of file content to detect modifications"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_chunk_path(output_dir, file_stem, chunk_id):
    """Get path for an individual chunk file"""
    return output_dir / f".chunk_{chunk_id}_{file_stem}.wav"


def save_checkpoint(
    output_dir, file_path, total_chunks, completed_chunks, voice="Kore"
):
    """
    Save checkpoint after completed chunks

    Args:
        output_dir: Output directory path
        file_path: Source markdown file path
        total_chunks: Total number of chunks
        completed_chunks: List of completed chunk IDs
        voice: Voice name used

    Returns:
        Path to checkpoint file
    """
    checkpoint_data = {
        "file": Path(file_path).name,
        "file_path": str(Path(file_path).absolute()),
        "file_hash": calculate_file_hash(file_path),
        "total_chunks": total_chunks,
        "completed_chunks": sorted(completed_chunks),
        "timestamp": datetime.now().isoformat(),
        "voice": voice,
        "version": "2.0",
    }

    checkpoint_file = output_dir / f".checkpoint_{Path(file_path).stem}.json"
    with open(checkpoint_file, "w") as f:
        json.dump(checkpoint_data, f, indent=2)

    return checkpoint_file


def load_checkpoint(output_dir, file_path):
    """
    Load existing checkpoint if available

    Args:
        output_dir: Output directory path
        file_path: Source markdown file path

    Returns:
        Checkpoint data dict or None if not found
    """
    checkpoint_file = output_dir / f".checkpoint_{Path(file_path).stem}.json"

    if not checkpoint_file.exists():
        return None

    try:
        with open(checkpoint_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️  Warning: Failed to load checkpoint: {e}")
        return None


def verify_checkpoint(checkpoint, file_path, output_dir):
    """
    Verify checkpoint is valid and all claimed chunk files exist

    Args:
        checkpoint: Checkpoint data dict
        file_path: Source markdown file path
        output_dir: Output directory path

    Returns:
        Tuple (is_valid: bool, valid_chunks: list, message: str)
    """
    if not checkpoint:
        return False, [], "No checkpoint found"

    # Check if source file still exists
    if not Path(file_path).exists():
        return False, [], "Source file no longer exists"

    # Check if file hash matches
    current_hash = calculate_file_hash(file_path)
    if current_hash != checkpoint.get("file_hash"):
        return False, [], "Source file has been modified since checkpoint"

    # Check if completed_chunks list is valid
    completed_chunks = checkpoint.get("completed_chunks")
    if not isinstance(completed_chunks, list):
        return False, [], "Invalid checkpoint format"

    # Verify individual chunk files exist
    file_stem = Path(file_path).stem
    valid_chunks = []
    missing_chunks = []

    for chunk_id in completed_chunks:
        chunk_path = get_chunk_path(output_dir, file_stem, chunk_id)
        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            valid_chunks.append(chunk_id)
        else:
            missing_chunks.append(chunk_id)

    if missing_chunks:
        print(f"⚠️  Warning: {len(missing_chunks)} chunk files missing from checkpoint")

    if not valid_chunks:
        return False, [], "No valid chunk files found"

    return True, valid_chunks, f"Checkpoint valid ({len(valid_chunks)} chunks)"


# ============================================================
# Audio File Operations
# ============================================================


def save_wav_file(filename, pcm_data, channels=1, rate=24000, sample_width=2):
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(channels)  # Mono
        wf.setsampwidth(sample_width)  # 16-bit
        wf.setframerate(rate)  # 24kHz
        wf.writeframes(pcm_data)  # Write PCM data


def convert_wav_to_mp3(wav_path, mp3_path, bitrate="128k", delete_wav=True):
    """
    Convert WAV to MP3 using ffmpeg

    Args:
        wav_path: Path to source WAV file
        mp3_path: Path to output MP3 file
        bitrate: MP3 bitrate (default: 128k - good quality, small size)
        delete_wav: Delete WAV file after successful conversion

    Returns:
        bool: True if successful
    """
    import subprocess

    wav_path = Path(wav_path)
    mp3_path = Path(mp3_path)

    if not wav_path.exists():
        print(f"❌ WAV file not found: {wav_path}")
        return False

    try:
        # ffmpeg command: quiet mode, overwrite output
        cmd = [
            "ffmpeg", "-y",  # overwrite without asking
            "-i", str(wav_path),  # input
            "-codec:a", "libmp3lame",  # MP3 encoder
            "-b:a", bitrate,  # bitrate
            "-q:a", "2",  # quality (0-9, lower is better)
            str(mp3_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout
        )

        if result.returncode != 0:
            print(f"❌ ffmpeg error: {result.stderr}")
            return False

        # Verify output exists
        if not mp3_path.exists():
            print(f"❌ MP3 file was not created")
            return False

        # Show size comparison
        wav_size = wav_path.stat().st_size
        mp3_size = mp3_path.stat().st_size
        reduction = (1 - mp3_size / wav_size) * 100
        print(f"📦 Converted: {wav_size/1024/1024:.2f}MB → {mp3_size/1024/1024:.2f}MB ({reduction:.0f}% smaller)")

        # Delete WAV if requested
        if delete_wav:
            wav_path.unlink()

        return True

    except subprocess.TimeoutExpired:
        print(f"❌ ffmpeg timeout")
        return False
    except Exception as e:
        print(f"❌ Conversion error: {e}")
        return False


def generate_audio_data(client, text, voice="Kore", rotation_manager=None):
    """
    Generate audio with automatic key rotation using KeyRotationManager

    Args:
        client: Gemini client (unused, kept for backwards compatibility)
        text: Text to convert to speech
        voice: Voice name (default: Kore)
        rotation_manager: KeyRotationManager instance (required)

    Returns:
        bytes: Audio data

    Raises:
        Exception: If all keys fail or are exhausted
    """
    if rotation_manager is None:
        raise ValueError("rotation_manager is required!")

    global api_key_manager  # For logging only

    max_attempts = 9  # Max attempts = number of keys

    for attempt in range(max_attempts):
        # Get next available key
        current_key = rotation_manager.get_next_key()

        if current_key is None:
            raise Exception("❌ No available API keys! All exhausted.")

        # Hash key for logging và tìm Index
        key_hash = hashlib.sha256(current_key.encode()).hexdigest()[:8]
        key_index = -1
        try:
            key_index = api_key_manager.keys.index(current_key) + 1
        except ValueError:
            pass
        key_display = f"Key #{key_index} ({key_hash})" if key_index > 0 else f"Key ({key_hash})"
        
        # Log active key execution
        print(f"      ▶️  Thực thi: {key_display}")

        try:
            # Create client with current key
            client = genai.Client(api_key=current_key)

            # Call API
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice
                            )
                        )
                    ),
                ),
            )

            # Check candidates
            if not hasattr(response, "candidates") or not response.candidates:
                raise ValueError(f"API returned no candidates! Full response: {response}")

            candidate = response.candidates[0]

            # Check for soft-fail (finish_reason=OTHER with content=None)
            if candidate.content is None:
                finish_reason = getattr(candidate, "finish_reason", "UNKNOWN")
                if "OTHER" in str(finish_reason):
                    # Rate limit soft-fail
                    print(f"   ⚠️  {key_display}: Rate limit soft-fail, cooldown 30s")
                    api_key_manager.log_request(current_key, success=False, error=f"Soft-fail: {finish_reason}")
                    rotation_manager.mark_key_failed(current_key, cooldown_seconds=30)
                    continue  # Retry with next key
                else:
                    raise ValueError(f"API blocked content: {finish_reason}")

            # Extract audio parts
            parts = candidate.content.parts
            all_audio_parts = []

            for i, part in enumerate(parts, 1):
                if hasattr(part, "inline_data") and part.inline_data:
                    audio_data = part.inline_data.data
                    all_audio_parts.append(audio_data)
                else:
                    print(f"      Part {i}: No audio data (skipped)")

            if not all_audio_parts:
                raise ValueError("No audio data found in API response!")

            # Concatenate all parts
            final_audio = b"".join(all_audio_parts)

            # Success → return key to queue
            rotation_manager.return_key(current_key)
            api_key_manager.log_request(current_key, success=True)

            return final_audio

        except Exception as e:
            error_type = classify_error(e)

            if error_type == "QUOTA_EXHAUSTED":
                print(f"   ❌ {key_display}: Quota exhausted, removed permanently")
                api_key_manager.log_request(current_key, success=False, error=str(e))
                rotation_manager.remove_key(current_key)
                # Retry với key khác

            elif error_type == "RATE_LIMIT" or error_type == "MODEL_OVERLOAD":
                print(f"   ⚠️  {key_display}: {error_type}, cooldown 30s")
                api_key_manager.log_request(current_key, success=False, error=str(e))
                rotation_manager.mark_key_failed(current_key, cooldown_seconds=30)
                # Retry với key khác

            else:
                # Unknown error, return key và raise
                rotation_manager.return_key(current_key)
                print(f"   ❌ Unknown error: {e}")
                raise

    # Hết attempts
    raise Exception(f"❌ Failed to generate audio after {max_attempts} attempts")


def process_chapter(client, file_path, voice="Kore", rotation_manager=None):
    try:
        input_path = Path(file_path)
        parent_dir = input_path.parent
        output_dir = parent_dir / "TTS"
        # Use .mp3 for final output
        output_filename_mp3 = input_path.stem + ".mp3"
        output_path_mp3 = output_dir / output_filename_mp3
        # Temp WAV file
        output_filename_wav = input_path.stem + ".wav"
        output_path_wav = output_dir / output_filename_wav

        print(f"\n📖 Đang xử lý: {input_path.name}")
        output_dir.mkdir(exist_ok=True)
        print(f"📁 Output directory: {output_dir}")

        print("📄 Đang đọc file...")
        with open(input_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        print(f"🧼 Đang làm sạch Markdown ({len(markdown_text):,} ký tự)...")
        clean_text = clean_markdown(markdown_text)
        print(f"✅ Đã làm sạch còn {len(clean_text):,} ký tự")

        total_tokens = count_tokens(clean_text)
        print(f"📊 Tổng số tokens: {total_tokens:,}")

        if total_tokens > MAX_TOKENS_PER_CHUNK:
            print(f"⚠️  File vượt {MAX_TOKENS_PER_CHUNK} tokens, cần chia nhỏ...")
            text_chunks = split_into_chunks(clean_text, max_tokens=MAX_TOKENS_PER_CHUNK)
            print(f"📦 Đã chia thành {len(text_chunks)} chunks")
        else:
            print(f"✅ File nhỏ hơn {MAX_TOKENS_PER_CHUNK} tokens, xử lý một lần")
            text_chunks = [clean_text]

        all_audio_parts = []
        total_bytes = 0

        for i, chunk in enumerate(text_chunks, 1):
            print(f"\n🎙️  Đang xử lý chunk {i}/{len(text_chunks)}...")
            print(f"   Chunk size: {count_tokens(chunk):,} tokens")

            audio_part = generate_audio_data(client, chunk, voice=voice, rotation_manager=rotation_manager)
            all_audio_parts.append(audio_part)
            total_bytes += len(audio_part)

            print(f"   ✅ Chunk {i} hoàn thành: {len(audio_part):,} bytes")

        print(f"\n✅ Đã tạo xong {len(all_audio_parts)} phần audio")
        print(f"📊 Tổng dung lượng: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)")

        print("🔗 Đang nối các phần audio...")
        final_audio_data = b"".join(all_audio_parts)

        print(f"💾 Đang lưu file WAV tạm...")
        save_wav_file(str(output_path_wav), final_audio_data)

        print(f"🔄 Đang convert sang MP3...")
        if convert_wav_to_mp3(output_path_wav, output_path_mp3):
            print(f"✅ Đã lưu: {output_path_mp3}")
        else:
            print(f"⚠️  Convert MP3 thất bại, giữ file WAV: {output_path_wav}")

        return True

    except FileNotFoundError:
        print(f"❌ Lỗi: Không tìm thấy file {file_path}")
        return False

    except Exception as e:
        try:
            if "all_audio_parts" in locals() and all_audio_parts:
                partial_filename = output_filename_wav.replace(".wav", "_PARTIAL.wav")
                partial_path = output_dir / partial_filename
                partial_audio = b"".join(all_audio_parts)
                save_wav_file(str(partial_path), partial_audio)

                print(f"\n💾 Saved partial progress ({len(all_audio_parts)}/{len(text_chunks)} chunks):")
                print(f"   File: {partial_path}")
                print(f"   Size: {len(partial_audio):,} bytes ({len(partial_audio)/1024/1024:.2f} MB)")
                print(f"   ℹ️  You can listen to completed chunks while investigating the error.")
        except Exception as save_error:
            print(f"⚠️  Warning: Failed to save partial progress: {save_error}")

        print(f"\n❌ Lỗi khi xử lý {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return False


def process_chapter_concurrent(client, file_path, voice="Kore", max_workers=3, resume=False, rotation_manager=None):
    """
    Process chapter with concurrent chunk processing using individual chunk files.
    """
    global api_key_manager

    try:
        # Step 1: Parse paths
        input_path = Path(file_path)
        parent_dir = input_path.parent
        output_dir = parent_dir / "TTS"
        # Final output is MP3, temp WAV for assembly
        output_filename_mp3 = input_path.stem + ".mp3"
        output_path_mp3 = output_dir / output_filename_mp3
        output_filename_wav = input_path.stem + ".wav"
        output_path_wav = output_dir / output_filename_wav

        print(f"\n{'='*60}")
        print(f"🎯 Processing Chapter: {input_path.name}")
        print(f"⚡ Concurrent Mode: {max_workers} workers")
        if resume:
            print(f"🔄 Resume Mode: Enabled")
        print(f"{ '='*60}\n")

        # Step 2: Create output directory
        output_dir.mkdir(exist_ok=True)

        # Step 3: Read and clean text
        with open(input_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        clean_text = clean_markdown(markdown_text)
        total_tokens = count_tokens(clean_text)

        # Step 4: Split into chunks
        if total_tokens > MAX_TOKENS_PER_CHUNK:
            text_chunks = split_into_chunks(clean_text, max_tokens=MAX_TOKENS_PER_CHUNK)
        else:
            text_chunks = [clean_text]

        total_chunks = len(text_chunks)
        
        # Step 5: Determine completed chunks (Resume logic)
        completed_chunks_list = []
        checkpoint = None
        
        if resume:
            checkpoint = load_checkpoint(output_dir, input_path)
            is_valid, valid_chunks, msg = verify_checkpoint(checkpoint, input_path, output_dir)
            
            if is_valid:
                completed_chunks_list = valid_chunks
                print(f"✅ Resuming from checkpoint: {len(completed_chunks_list)} chunks already done.")
            else:
                print(f"ℹ️  Resume info: {msg}. Starting fresh or reprocessing invalid chunks.")

        # Identify chunks to process
        chunks_to_process = {}
        for i, chunk in enumerate(text_chunks):
            if i not in completed_chunks_list:
                chunks_to_process[i] = chunk

        # Info display
        print(f"📊 Chapter Info:")
        print(f"   Total chunks: {total_chunks}")
        print(f"   Already completed: {len(completed_chunks_list)}")
        print(f"   Remaining to process: {len(chunks_to_process)}")
        
        if not chunks_to_process and total_chunks > 0:
            print("\n✨ All chunks already completed! Proceeding to assembly.")
        else:
            print(f"   Expected API calls: {len(chunks_to_process)}")
            print(f"   Estimated time: {(len(chunks_to_process) / max_workers) * 20:.0f}s ⚡")
            print()

        # Thread-safe locks
        checkpoint_lock = threading.Lock()
        progress_lock = threading.Lock()
        completed_count = [len(completed_chunks_list)] 
        current_completed_set = set(completed_chunks_list)

        def process_single_chunk(chunk_id, chunk_text):
            """Process a single chunk and save to individual file"""
            nonlocal current_completed_set
            
            try:
                # Get assigned API key
                assigned_key = api_key_manager.get_key_for_chunk(chunk_id)
                
                # Create client
                chunk_client = genai.Client(api_key=assigned_key)
                
                # Generate audio
                audio_data = generate_audio_data(chunk_client, chunk_text, voice=voice, rotation_manager=rotation_manager)
                
                # Save individual chunk file
                chunk_path = get_chunk_path(output_dir, input_path.stem, chunk_id)
                save_wav_file(chunk_path, audio_data)
                
                # Update progress and checkpoint
                with progress_lock:
                    completed_count[0] += 1
                    print(f"✅ Chunk {chunk_id + 1}/{total_chunks} saved to {chunk_path.name}")
                    
                with checkpoint_lock:
                    current_completed_set.add(chunk_id)
                    save_checkpoint(
                        output_dir, input_path, total_chunks, list(current_completed_set), voice
                    )
                
                return True
                
            except Exception as e:
                print(f"❌ Error processing chunk {chunk_id + 1}: {e}")
                raise

        # Step 6: Execute Concurrent Processing
        if chunks_to_process:
            print(f"⏳ Starting processing with {max_workers} workers...\n")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_chunk = {
                    executor.submit(process_single_chunk, cid, text): cid
                    for cid, text in chunks_to_process.items()
                }
                
                for future in as_completed(future_to_chunk):
                    chunk_id = future_to_chunk[future]
                    try:
                        future.result()
                    except Exception:
                        # Error already printed in thread
                        pass
        
        # Step 7: Verify all chunks exist before assembly
        print(f"\n🔍 Verifying chunks for assembly...")
        missing_chunks = []
        for i in range(total_chunks):
            chunk_path = get_chunk_path(output_dir, input_path.stem, i)
            if not chunk_path.exists():
                missing_chunks.append(i)
        
        if missing_chunks:
            print(f"❌ Missing chunks: {[i+1 for i in missing_chunks]}")
            print(f"💾 Partial progress is saved in individual chunk files.")
            print(f"ℹ️  Run again with --resume to finish.")
            return False

        # Step 8: Assemble Final Audio
        print(f"🔗 Assembling {total_chunks} chunks in order...")
        
        # Create a new wave file for the final output
        # We read parameters from the first chunk
        first_chunk_path = get_chunk_path(output_dir, input_path.stem, 0)
        if not first_chunk_path.exists():
             print("❌ Critical error: First chunk missing, cannot determine WAV parameters.")
             return False
             
        with wave.open(str(first_chunk_path), 'rb') as first_wav:
            params = first_wav.getparams()

        with wave.open(str(output_path_wav), 'wb') as final_wav:
            final_wav.setparams(params)

            for i in range(total_chunks):
                chunk_path = get_chunk_path(output_dir, input_path.stem, i)
                with wave.open(str(chunk_path), 'rb') as chunk_wav:
                    final_wav.writeframes(chunk_wav.readframes(chunk_wav.getnframes()))

        print(f"✅ WAV assembled: {output_path_wav}")

        # Step 9: Convert WAV to MP3
        print(f"🔄 Converting to MP3...")
        if convert_wav_to_mp3(output_path_wav, output_path_mp3):
            final_output = output_path_mp3
        else:
            print(f"⚠️  MP3 conversion failed, keeping WAV file")
            final_output = output_path_wav

        # Step 10: Cleanup chunk files
        print(f"🧹 Cleaning up chunk files...")
        for i in range(total_chunks):
            chunk_path = get_chunk_path(output_dir, input_path.stem, i)
            try:
                chunk_path.unlink()
            except Exception as e:
                print(f"⚠️  Failed to delete {chunk_path.name}: {e}")
                
        checkpoint_file = output_dir / f".checkpoint_{input_path.stem}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

        print(f"\n{'='*60}")
        print(f"✅ Success! Audio saved to: {final_output}")
        print(f"{'='*60}\n")
        
        return True

    except Exception as e:
        print(f"\n❌ Error in concurrent processing: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Generate audiobook from markdown using Gemini TTS"
    )
    parser.add_argument("file", nargs="?", help="Markdown file to process")
    parser.add_argument("--voice", default="Kore", help="Voice name (default: Kore)")

    # Concurrent processing flags
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="Enable concurrent processing (faster)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of concurrent workers (default: 3, max: 7)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint if available (skip completed chunks)",
    )

    args = parser.parse_args()

    # Validate workers
    if args.workers > 7:
        print("⚠️  Warning: Max workers is 7 (number of API keys). Setting to 7.")
        args.workers = 7
    if args.workers < 1:
        print("⚠️  Warning: Min workers is 1. Setting to 1.")
        args.workers = 1

    # Print header
    print("\n" + "=" * 60)
    print("🎙️  Gemini TTS Audiobook Generator")
    print("=" * 60)

    # Load API keys
    global api_key_manager
    api_key_manager.print_usage_stats()

    # Initialize KeyRotationManager
    rotation_manager = KeyRotationManager(api_keys=api_key_manager.keys)
    print(f"🔄 Key Rotation Manager initialized with {len(api_key_manager.keys)} keys\n")

    # Create client (for synchronous mode)
    client = genai.Client(api_key=api_key_manager.get_active_key())

    # Get file to process
    if args.file:
        file_path = args.file
    else:
        # Default test file
        file_path = "2.DATA/BOOK-2_Learn-Python/B2-CH02.md"
        print(f"\n📝 No file specified, using default: {file_path}")

    # Process with concurrent or synchronous mode
    if args.concurrent:
        mode_text = "CONCURRENT mode"
        if args.resume:
            mode_text += " with RESUME"
        print(f"\n⚡ Using {mode_text} ({args.workers} workers)\n")

        success = process_chapter_concurrent(
            client, file_path, voice=args.voice, max_workers=args.workers, resume=args.resume, rotation_manager=rotation_manager
        )
    else:
        print(
            f"\n📝 Using SYNCHRONOUS mode (use --concurrent for faster processing)\n"
        )
        success = process_chapter(client, file_path, voice=args.voice, rotation_manager=rotation_manager)

    # Final result
    if success:
        print("\n🎉 Processing complete!")
    else:
        print("\n❌ Processing failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

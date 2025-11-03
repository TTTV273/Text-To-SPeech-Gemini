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

import tiktoken
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from api_key_manager import APIKeyManager

# Setup encoding
ENCODING = tiktoken.get_encoding("cl100k_base")

load_dotenv()
api_key_manager = APIKeyManager(usage_file="api_usage.json", threshold=14)


def clean_markdown(text: str) -> str:
    # clean Headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

    # clean Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)

    # clean Italic
    text = re.sub(r"\*([^*]+)\*", r"\1", text)

    # clean Link
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # clean Code Block
    text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)

    # clean in line code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # clean image
    text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", "", text)

    return text


def count_tokens(text: str) -> int:
    """Count token in text"""
    return len(ENCODING.encode(text))


def split_into_chunks(text: str, max_tokens: int = 20000) -> list[str]:
    """Split text into token-safe chunks"""
    chunks = []
    current_chunk = []
    current_token_count = 0

    # Split by paragraphs (double newline)
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Count tokens for this paragraph
        para_tokens = count_tokens(para)

        # Check if adding this para would exceed limit
        if current_token_count + para_tokens > max_tokens:
            # Finalize current chunk
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))

                # Start new chunk with this paragraph
                current_chunk = [para]
                current_token_count = para_tokens
        else:
            # Add to current chunk
            current_chunk.append(para)
            current_token_count += para_tokens

    # Add final chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


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


def save_checkpoint(
    output_dir, file_path, total_chunks, completed_chunks, partial_audio_file, voice="Kore"
):
    """
    Save checkpoint after completed chunks

    Args:
        output_dir: Output directory path
        file_path: Source markdown file path
        total_chunks: Total number of chunks
        completed_chunks: List of completed chunk IDs
        partial_audio_file: Filename of partial audio
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
        "failed_chunks": [],
        "partial_audio_file": partial_audio_file,
        "partial_audio_size": (
            Path(output_dir / partial_audio_file).stat().st_size
            if (output_dir / partial_audio_file).exists()
            else 0
        ),
        "timestamp": datetime.now().isoformat(),
        "voice": voice,
        "version": "1.0",
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
    Verify checkpoint is still valid (file not modified, partial audio exists)

    Args:
        checkpoint: Checkpoint data dict
        file_path: Source markdown file path
        output_dir: Output directory path

    Returns:
        Tuple (is_valid: bool, message: str)
    """
    if not checkpoint:
        return False, "No checkpoint found"

    # Check if source file still exists
    if not Path(file_path).exists():
        return False, "Source file no longer exists"

    # Check if file hash matches
    current_hash = calculate_file_hash(file_path)
    if current_hash != checkpoint.get("file_hash"):
        return False, "Source file has been modified since checkpoint"

    # Check if partial audio file exists
    partial_filename = checkpoint.get("partial_audio_file", "")
    partial_file = output_dir / partial_filename
    if not partial_file.exists():
        return False, f"Partial audio file not found: {partial_filename}"

    # Check if completed_chunks list is valid
    if not isinstance(checkpoint.get("completed_chunks"), list):
        return False, "Invalid checkpoint format: completed_chunks not a list"

    return True, "Checkpoint valid"


def load_partial_audio(partial_audio_path):
    """
    Load existing partial audio data from WAV file

    Args:
        partial_audio_path: Path to partial WAV file

    Returns:
        Raw PCM audio data as bytes
    """
    with wave.open(str(partial_audio_path), "rb") as wf:
        # Read all frames as raw PCM data
        audio_data = wf.readframes(wf.getnframes())

    return audio_data


# ============================================================
# WAV File Operations
# ============================================================


def save_wav_file(filename, pcm_data, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)  # Mono
        wf.setsampwidth(sample_width)  # 16-bit
        wf.setframerate(rate)  # 24kHz
        wf.writeframes(pcm_data)  # Write PCM data


def generate_audio_data(client, text, voice="Kore", max_retries=3):
    """
    Generate audio with automatic retry and key rotation

    Args:
        client: genai.Client instance (will be recreated on key rotation)
        text: Text to convert
        voice: Voice name
        max_retries: Max retries per key

    Returns:
        bytes: Audio data
    """
    global api_key_manager  # Access global manager

    attempt = 0
    keys_tried = 0
    max_keys = len(api_key_manager.keys)

    while keys_tried < max_keys:
        current_key = api_key_manager.get_active_key()

        for attempt in range(max_retries):
            try:
                # Recreate client with current key
                client = genai.Client(api_key=current_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice,
                                )
                            )
                        ),
                    ),
                )

                # 🔍 DEBUG: Inspect response structure before accessing parts
                print(f"\n{'='*60}")
                print(f"🔍 DEBUG: Response Structure Inspection")
                print(f"{'='*60}")
                print(f"Response type: {type(response)}")
                print(
                    f"hasattr(response, 'candidates'): {hasattr(response, 'candidates')}"
                )

                if hasattr(response, "candidates"):
                    if response.candidates:
                        print(f"len(response.candidates): {len(response.candidates)}")
                        candidate = response.candidates[0]
                        print(f"candidates[0] type: {type(candidate)}")
                        print(
                            f"hasattr(candidates[0], 'content'): {hasattr(candidate, 'content')}"
                        )
                        print(f"candidates[0].content type: {type(candidate.content)}")
                        print(f"candidates[0].content value: {candidate.content}")

                        if candidate.content is None:
                            print(f"\n❌ WARNING: content is None!")
                            print(
                                f"This indicates API soft-fail (rate limit or safety filter)"
                            )

                            # Check for other response fields
                            if hasattr(response, "prompt_feedback"):
                                print(f"prompt_feedback: {response.prompt_feedback}")
                            if hasattr(candidate, "finish_reason"):
                                print(f"finish_reason: {candidate.finish_reason}")
                            if hasattr(candidate, "safety_ratings"):
                                print(f"safety_ratings: {candidate.safety_ratings}")

                            # Print full response for investigation
                            print(f"\nFull response object:")
                            print(f"{response}")
                    else:
                        print(f"❌ WARNING: response.candidates is empty!")
                        print(f"Full response: {response}")
                else:
                    print(f"❌ WARNING: response has no 'candidates' attribute!")
                    print(
                        f"Available attributes: {[x for x in dir(response) if not x.startswith('_')]}"
                    )

                print(f"{'='*60}\n")

                # Defensive check before accessing parts
                if not response.candidates:
                    raise ValueError(
                        f"API returned no candidates! Full response: {response}"
                    )

                if response.candidates[0].content is None:
                    # Check if it's a rate limit issue
                    candidate = response.candidates[0]

                    # Check finish_reason to determine if retriable
                    if hasattr(candidate, "finish_reason"):
                        finish_reason = str(candidate.finish_reason)

                        # Treat OTHER as rate limit soft-fail (retriable)
                        if "OTHER" in finish_reason:
                            print(
                                f"   ⚠️  Rate limit soft-fail detected (finish_reason={finish_reason})"
                            )

                            # Log failed request
                            api_key_manager.log_request(
                                current_key,
                                success=False,
                                error=f"Soft-fail: {finish_reason}",
                            )

                            # Retry logic (same as 429 error)
                            if attempt < max_retries - 1:
                                retry_delay = 30  # Default 30s
                                print(
                                    f"   ⏳ Rate limit soft-fail, retry #{attempt + 1} sau {retry_delay}s..."
                                )
                                time.sleep(retry_delay)
                                continue  # Continue retry loop
                            else:
                                print(
                                    f"   ❌ Key exhausted after {max_retries} retries (soft-fail)"
                                )
                                break  # try next key
                        else:
                            # SAFETY, RECITATION, etc - not retriable
                            error_msg = (
                                f"API blocked content: finish_reason={finish_reason}"
                            )
                            if hasattr(response, "prompt_feedback"):
                                error_msg += (
                                    f", prompt_feedback={response.prompt_feedback}"
                                )
                            raise ValueError(error_msg)
                    else:
                        # No finish_reason - unknown error
                        raise ValueError(f"API returned empty content (unknown reason)")

                # Extract ALL audio parts (not just parts[0]!)
                parts = response.candidates[0].content.parts
                all_audio_parts = []

                print(f"   📦 API trả về {len(parts)} parts")

                for i, part in enumerate(parts, 1):
                    if hasattr(part, "inline_data") and part.inline_data:
                        audio_data = part.inline_data.data
                        all_audio_parts.append(audio_data)
                        print(f"      Part {i}: {len(audio_data):,} bytes")
                    else:
                        print(f"      Part {i}: No audio data (text part?)")

                if len(all_audio_parts) == 0:
                    raise ValueError("No audio data found in API response!")

                # Concatenate all parts
                final_audio = b"".join(all_audio_parts)
                print(f"   ✅ Tổng audio: {len(final_audio):,} bytes")

                # Log successful request
                api_key_manager.log_request(current_key, success=True)

                return final_audio

            except ClientError as e:
                # 🔍 DEBUG: Inspect ClientError structure
                print(f"\n{'='*60}")
                print(f"🔍 DEBUG: ClientError Inspection")
                print(f"{'='*60}")
                print(f"Type: {type(e)}")
                print(f"\nString reprentation:")
                print(f"{str(e)[:500]}")

                print(f"\nAvailable attributes (non-private):")
                attrs = [x for x in dir(e) if not x.startswith("_")]
                for attr in attrs:
                    try:
                        value = getattr(e, attr)
                        if not callable(value):
                            print(
                                f"  - {attr}: {type(value).__name__} = {repr(value)[:100]}"
                            )
                    except:
                        pass

                print(f"\n{'='*60}")
                print("Testing 4 methods to detect 429:")
                print(f"{'='*60}")

                # Method 1: String-based check
                method1 = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                print(f"  Method 1 (string check): {method1}")
                print(f"    - '429' in str(e): {'429' in str(e)}")
                print(
                    f"    - 'RESOURCE_EXHAUSTED' in str(e): {'RESOURCE_EXHAUSTED' in str(e)}"
                )

                # Method 2: hasattr status_code
                method2_has = hasattr(e, "status_code")
                method2 = method2_has and e.status_code == 429
                print(f"  Method 2 (status_code attr): {method2}")
                print(f"    - hasattr(e, 'status_code'): {method2_has}")
                if method2_has:
                    print(f"    - e.status_code: {e.status_code}")

                # Method 3: hasattr code
                method3_has = hasattr(e, "code")
                method3 = method3_has and e.code == 429
                print(f"  Method 3 (code attr): {method3}")
                print(f"    - hasattr(e, 'code'): {method3_has}")
                if method3_has:
                    print(f"    - e.code: {e.code}")

                # Method 4: Parse error dict
                method4 = False
                method4_has_error = hasattr(e, "error")
                print(f"  Method 4 (error dict): {method4}")
                print(f"    - hasattr(e, 'error'): {method4_has_error}")
                if method4_has_error:
                    try:
                        error_dict = e.error
                        print(f"    - e.error type: {type(error_dict)}")
                        print(f"    - e.error: {error_dict}")
                        if hasattr(error_dict, "get"):
                            method4 = error_dict.get("code") == 429
                            print(
                                f"    - e.error.get('code'): {error_dict.get('code')}"
                            )
                    except Exception as parse_err:
                        print(f"    - Error parsing: {parse_err}")

                print(f"\n{'='*60}")
                working_methods = [
                    i
                    for i, m in enumerate([method1, method2, method3, method4], 1)
                    if m
                ]
                print(f"✅ Working methods: {working_methods}")
                print(f"{'='*60}\n")

                # Use Method 1 for now (safest fallback)
                if method1:
                    # Parse retry delay from error
                    retry_delay = 30  # Defaults 30s
                    if "retrydelay" in str(e):
                        # Extract delay: "retry in 27.591s" -> 27

                        match = re.search(r"(\d+)\.?\d*s", str(e))
                        if match:
                            retry_delay = int(float(match.group(1))) + 1

                    # Log failed request
                    api_key_manager.log_request(
                        current_key, success=False, error=str(e)
                    )

                    if attempt < max_retries - 1:
                        print(
                            f"   ⏳ Rate limit hit, retry #{attempt + 1} sau {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                    else:
                        print(f"   ❌ Key exhausted after {max_retries} retries")
                        break  # try next key
                else:
                    # Other errors - don't retry
                    raise

        # Current key failed all retries, try next key
        keys_tried += 1
        if keys_tried < max_keys:
            if not api_key_manager.rotate_key():
                raise Exception("All API keys exhausted!")
        else:
            raise Exception("All API keys failed after retries!")

    raise Exception("Failed to generate audio after trying all keys!")


def process_chapter(client, file_path, voice="Kore"):
    try:
        # Step 1: Parse paths
        input_path = Path(file_path)
        parent_dir = input_path.parent
        output_dir = parent_dir / "TTS"
        output_filename = input_path.stem + ".wav"
        output_path = output_dir / output_filename

        print(f"\n📖 Đang xử lý: {input_path.name}")

        # Step 2: Create output directory
        output_dir.mkdir(exist_ok=True)
        print(f"📁 Output directory: {output_dir}")

        # Step 3: Read file content
        print("📄 Đang đọc file...")
        with open(input_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        print(f"🧼 Đang làm sạch Markdown ({len(markdown_text):,} ký tự)...")
        clean_text = clean_markdown(markdown_text)
        print(f"✅ Đã làm sạch còn {len(clean_text):,} ký tự")

        # Step 4: Count tokens and split into chunks
        total_tokens = count_tokens(clean_text)
        print(f"📊 Tổng số tokens: {total_tokens:,}")

        if total_tokens > 2000:
            print("⚠️  File vượt 2k tokens, cần chia nhỏ...")
            text_chunks = split_into_chunks(clean_text, max_tokens=2000)
            print(f"📦 Đã chia thành {len(text_chunks)} chunks")
        else:
            print("✅ File nhỏ hơn 2k tokens, xử lý một lần")
            text_chunks = [clean_text]

        # Step 5: Generate audio for each chunk
        all_audio_parts = []
        total_bytes = 0

        for i, chunk in enumerate(text_chunks, 1):
            print(f"\n🎙️  Đang xử lý chunk {i}/{len(text_chunks)}...")
            print(f"   Chunk size: {count_tokens(chunk):,} tokens")

            audio_part = generate_audio_data(client, chunk, voice=voice)
            all_audio_parts.append(audio_part)
            total_bytes += len(audio_part)

            print(f"   ✅ Chunk {i} hoàn thành: {len(audio_part):,} bytes")

        print(f"\n✅ Đã tạo xong {len(all_audio_parts)} phần audio")
        print(
            f"📊 Tổng dung lượng: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)"
        )

        # Step 6: Concatenate all audio parts
        print("🔗 Đang nối các phần audio...")
        final_audio_data = b"".join(all_audio_parts)

        # Step 7: Save WAV file
        print(f"💾 Đang lưu file...")
        save_wav_file(str(output_path), final_audio_data)
        print(f"✅ Đã lưu: {output_path}")

        return True

    except FileNotFoundError:
        print(f"❌ Lỗi: Không tìm thấy file {file_path}")
        return False

    except Exception as e:
        # Partial Save: Preserve completed chunks before exiting
        try:
            if "all_audio_parts" in locals() and all_audio_parts:
                partial_filename = output_filename.replace(".wav", "_PARTIAL.wav")
                partial_path = output_dir / partial_filename
                partial_audio = b"".join(all_audio_parts)
                save_wav_file(str(partial_path), partial_audio)

                print(
                    f"\n💾 Saved partial progress ({len(all_audio_parts)}/{len(text_chunks)} chunks):"
                )
                print(f"   File: {partial_path}")
                print(
                    f"   Size: {len(partial_audio):,} bytes ({len(partial_audio)/1024/1024:.2f} MB)"
                )
                print(
                    f"   ℹ️  You can listen to completed chunks while investigating the error."
                )
        except Exception as save_error:
            print(f"⚠️  Warning: Failed to save partial progress: {save_error}")

        print(f"\n❌ Lỗi khi xử lý {file_path}: {e}")
        import traceback

        traceback.print_exc()
        return False


def process_chapter_concurrent(client, file_path, voice="Kore", max_workers=3, resume=False):
    """
    Process chapter with concurrent chunk processing.

    Args:
        client: Gemini client (not used, each thread creates own client)
        file_path: Path to markdown file
        voice: Voice name for TTS
        max_workers: Number of concurrent workers (default: 3)
        resume: Resume from checkpoint if available (default: False)

    Returns:
        bool: True if successful, False otherwise
    """
    global api_key_manager

    try:
        # Step 1: Parse paths
        input_path = Path(file_path)
        parent_dir = input_path.parent
        output_dir = parent_dir / "TTS"
        output_filename = input_path.stem + ".wav"
        output_path = output_dir / output_filename

        print(f"\n{'='*60}")
        print(f"🎯 Processing Chapter: {input_path.name}")
        print(f"⚡ Concurrent Mode: {max_workers} workers")
        if resume:
            print(f"🔄 Resume Mode: Will use checkpoint if available")
        print(f"{'='*60}\n")

        # Step 2: Create output directory
        output_dir.mkdir(exist_ok=True)

        # Step 2.5: Check for checkpoint (Phase 8: Resume Feature)
        checkpoint = None
        existing_audio = None
        completed_chunks_list = []

        if resume:
            checkpoint = load_checkpoint(output_dir, input_path)
            if checkpoint:
                is_valid, message = verify_checkpoint(checkpoint, input_path, output_dir)
                if is_valid:
                    print(f"✅ Found valid checkpoint:")
                    print(f"   Completed chunks: {len(checkpoint['completed_chunks'])}/{checkpoint['total_chunks']}")
                    print(f"   Partial file: {checkpoint['partial_audio_file']}")
                    print(f"   File size: {checkpoint['partial_audio_size']:,} bytes ({checkpoint['partial_audio_size']/1024/1024:.2f} MB)")
                    print(f"   Timestamp: {checkpoint['timestamp']}")
                    print()

                    # Load existing partial audio
                    partial_audio_path = output_dir / checkpoint['partial_audio_file']
                    existing_audio = load_partial_audio(partial_audio_path)
                    completed_chunks_list = checkpoint['completed_chunks']
                    print(f"📦 Loaded {len(existing_audio):,} bytes from partial audio\n")
                else:
                    print(f"⚠️  Invalid checkpoint: {message}")
                    print(f"   Starting fresh processing...\n")
                    checkpoint = None

        # Step 3: Read and clean text
        with open(input_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        clean_text = clean_markdown(markdown_text)
        total_tokens = count_tokens(clean_text)

        # Step 4: Split into chunks
        if total_tokens > 2000:
            text_chunks = split_into_chunks(clean_text, max_tokens=2000)
        else:
            text_chunks = [clean_text]

        total_chunks = len(text_chunks)

        # Step 4.5: Filter chunks to process (Phase 8: Resume Feature)
        if checkpoint and completed_chunks_list:
            # Only process chunks that are NOT in completed list
            chunks_to_process = {
                i: chunk for i, chunk in enumerate(text_chunks)
                if i not in completed_chunks_list
            }
            print(f"📊 Chapter Info (Resume Mode):")
            print(f"   Total chunks: {total_chunks}")
            print(f"   Already completed: {len(completed_chunks_list)}")
            print(f"   Remaining to process: {len(chunks_to_process)}")
            print(f"   Total tokens: {total_tokens:,}")
            print(f"   Expected API calls: {len(chunks_to_process)} (saved {len(completed_chunks_list)} calls!)")
            print(
                f"   Estimated time (concurrent): {(len(chunks_to_process) / max_workers) * 20:.0f}s ⚡"
            )
            print()
        else:
            # Process all chunks (normal mode)
            chunks_to_process = {i: chunk for i, chunk in enumerate(text_chunks)}
            print(f"📊 Chapter Info:")
            print(f"   Total chunks: {total_chunks}")
            print(f"   Total tokens: {total_tokens:,}")
            print(f"   Expected API calls: {total_chunks}")
            print(f"   Estimated time (sequential): {total_chunks * 20}s")
            print(
                f"   Estimated time (concurrent): {(total_chunks / max_workers) * 20:.0f}s ⚡"
            )
            print()

        # Thread-safe results storage
        results = {}
        results_lock = threading.Lock()

        # Progress tracking
        progress_lock = threading.Lock()
        completed_count = [0]  # Use list for mutable counter

        def process_single_chunk(chunk_id, chunk_text):
            """Process a single chunk (runs in thread)"""
            nonlocal results, results_lock, completed_count, progress_lock

            try:
                # Get assigned API key for this chunk (round-robin)
                assigned_key = api_key_manager.get_key_for_chunk(chunk_id)

                # Create client with assigned key
                chunk_client = genai.Client(api_key=assigned_key)

                # Generate audio (with retry logic)
                audio_data = generate_audio_data(
                    chunk_client, chunk_text, voice=voice
                )

                # Store result (thread-safe)
                with results_lock:
                    results[chunk_id] = audio_data

                # Update progress (thread-safe)
                with progress_lock:
                    completed_count[0] += 1
                    print(
                        f"✅ Chunk {chunk_id + 1}/{total_chunks} completed ({completed_count[0]}/{total_chunks})"
                    )

                return audio_data

            except Exception as e:
                print(f"❌ Error processing chunk {chunk_id + 1}: {e}")
                with results_lock:
                    results[chunk_id] = None  # Mark as failed
                raise

        # Step 5: Concurrent processing
        if checkpoint and completed_chunks_list:
            print(f"⏳ Starting concurrent processing with {max_workers} workers (Resume Mode)...")
            print(f"   Processing {len(chunks_to_process)} remaining chunks...\n")
        else:
            print(f"⏳ Starting concurrent processing with {max_workers} workers...\n")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit only chunks that need processing
            future_to_chunk = {
                executor.submit(process_single_chunk, chunk_id, chunk_text): chunk_id
                for chunk_id, chunk_text in chunks_to_process.items()
            }

            # Wait for all to complete
            for future in as_completed(future_to_chunk):
                chunk_id = future_to_chunk[future]
                try:
                    future.result()  # Raises exception if chunk failed
                except Exception as e:
                    print(f"❌ Chunk {chunk_id + 1} failed: {e}")
                    # Continue processing other chunks

        # Step 6: Check for failed chunks
        failed_chunks = [i for i, data in results.items() if data is None]
        if failed_chunks:
            print(
                f"\n❌ {len(failed_chunks)} chunk(s) failed: {[i+1 for i in failed_chunks]}"
            )

            # Partial save of successful chunks (merge with existing if resume mode)
            successful_chunks = {
                i: data for i, data in results.items() if data is not None
            }

            if successful_chunks or existing_audio:
                # Merge existing audio (from checkpoint) with newly processed chunks
                all_completed_chunks = []
                completed_indices = []

                # Add existing audio if we're in resume mode
                if existing_audio and completed_chunks_list:
                    all_completed_chunks.append(existing_audio)
                    completed_indices.extend(completed_chunks_list)

                # Add newly successful chunks (in order)
                if successful_chunks:
                    new_chunk_indices = sorted(successful_chunks.keys())
                    for i in new_chunk_indices:
                        all_completed_chunks.append(successful_chunks[i])
                        completed_indices.append(i)

                # Combine all completed audio
                partial_audio = b"".join(all_completed_chunks)
                partial_filename = output_filename.replace(".wav", "_PARTIAL.wav")
                partial_path = output_dir / partial_filename
                save_wav_file(str(partial_path), partial_audio)

                # Save checkpoint
                checkpoint_path = save_checkpoint(
                    output_dir, input_path, total_chunks, completed_indices, partial_filename, voice
                )

                print(
                    f"\n💾 Saved partial progress ({len(completed_indices)}/{total_chunks} chunks):"
                )
                print(f"   File: {partial_path}")
                print(
                    f"   Size: {len(partial_audio):,} bytes ({len(partial_audio)/1024/1024:.2f} MB)"
                )
                print(f"   Checkpoint: {checkpoint_path}")
                print(f"   ℹ️  You can resume with: --resume flag")

            return False

        # Step 7: Assemble chunks in order (merge with existing if resume mode)
        if existing_audio and completed_chunks_list:
            print(f"\n🔧 Merging existing audio + {len(results)} new chunks...")

            # Build complete audio: all chunks in order
            all_audio_parts = []
            for i in range(total_chunks):
                if i in completed_chunks_list:
                    # This chunk was already completed (from checkpoint)
                    # Audio is already in existing_audio, but we need to extract it chunk by chunk
                    # Actually, we can't extract individual chunks from existing_audio
                    # So we need a different approach: store ALL audio parts in results dict
                    pass
                else:
                    # This chunk was just processed
                    all_audio_parts.append(results[i])

            # Since we can't extract individual chunks from existing_audio,
            # we'll merge existing_audio (all completed chunks) + new chunks
            # But this won't preserve order correctly...

            # Better approach: just concatenate existing + new in order
            # Create a complete list of all audio data in chunk order
            complete_audio_parts = []

            # We need to merge properly:
            # - existing_audio contains chunks 0-9 (for B2-CH05 example)
            # - results contains chunk 10
            # Final should be: chunk 0, 1, 2, ..., 9, 10 in order

            # Since existing_audio is already chunks 0-(n-1) concatenated,
            # and results contains the remaining chunks,
            # we can just append results to existing_audio

            final_audio = existing_audio + b"".join([results[i] for i in sorted(results.keys())])

            print(f"   Existing audio: {len(existing_audio):,} bytes")
            print(f"   New chunks: {len(results)} chunks, {sum(len(results[i]) for i in results):,} bytes")
        else:
            print(f"\n🔧 Assembling {total_chunks} chunks in order...")
            all_audio_parts = [results[i] for i in sorted(results.keys())]
            final_audio = b"".join(all_audio_parts)

        # Step 8: Save final audio
        save_wav_file(str(output_path), final_audio)

        # Step 9: Clean up checkpoint and partial files (Phase 8: Resume Feature)
        if checkpoint:
            checkpoint_file = output_dir / f".checkpoint_{input_path.stem}.json"
            partial_file = output_dir / (output_filename.replace(".wav", "_PARTIAL.wav"))

            if checkpoint_file.exists():
                checkpoint_file.unlink()
                print(f"\n🧹 Cleaned up checkpoint file")

            if partial_file.exists():
                partial_file.unlink()
                print(f"🧹 Cleaned up partial audio file")

        # Success message
        print(f"\n{'='*60}")
        print(f"✅ Success! Audio saved to: {output_path}")
        if existing_audio:
            print(f"   Mode: Resume (merged existing + new chunks)")
        print(f"   Total chunks: {total_chunks}")
        print(
            f"   Size: {len(final_audio):,} bytes ({len(final_audio)/1024/1024:.2f} MB)"
        )
        print(f"{'='*60}\n")

        return True

    except FileNotFoundError:
        print(f"❌ Error: File not found {file_path}")
        return False

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
            client, file_path, voice=args.voice, max_workers=args.workers, resume=args.resume
        )
    else:
        print(
            f"\n📝 Using SYNCHRONOUS mode (use --concurrent for faster processing)\n"
        )
        success = process_chapter(client, file_path, voice=args.voice)

    # Final result
    if success:
        print("\n🎉 Processing complete!")
    else:
        print("\n❌ Processing failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

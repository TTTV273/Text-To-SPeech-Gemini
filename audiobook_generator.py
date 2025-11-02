import os
import re
import time
import wave
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
                # Check if 429 Rate Limit error
                if e.status_code == 429:
                    # Parse retry delay from error
                    retry_delay = 30  # Default 30s
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
        print(f"❌ Lỗi khi xử lý {file_path}: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    print("--- Bắt đầu quá trình tạo sách nói ---")
    api_key = api_key_manager.get_active_key()

    client = genai.Client(api_key=api_key)
    print("\n--- Môi trường đã sẵn sàng! ---")

    # === TEST PHASE 4: Chunking Support ===
    test_file = os.path.expanduser(
        "/Users/tttv/Library/Mobile Documents/com~apple~CloudDocs/Ebook/Robert Jordan/The Complete Wheel of Time (422)/B2/B2-CH01.md"
    )
    success = process_chapter(client, test_file, voice="Kore")

    if success:
        print("\n🎉 Phase 4 test PASSED!")
    else:
        print("\n❌ Phase 4 test FAILED!")


if __name__ == "__main__":
    main()

import os
import re
import sys
import wave
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Setup encoding
ENCODING = tiktoken.get_encoding("cl100k_base")

load_dotenv()


def check_environment():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("LỖI: Biến môi trường 'GEMINI_API_KEY' không được tìm thấy.")
        sys.exit(1)

    print("✅ Đã tìm thấy GEMINI_API_KEY.")
    return api_key


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


def generate_audio_data(client, text, voice="Kore"):
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

    # Extract PCM data from response
    pcm_data = response.candidates[0].content.parts[0].inline_data.data
    return pcm_data


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

        if total_tokens > 20000:
            print("⚠️  File vượt 20k tokens, cần chia nhỏ...")
            text_chunks = split_into_chunks(clean_text, max_tokens=20000)
            print(f"📦 Đã chia thành {len(text_chunks)} chunks")
        else:
            print("✅ File nhỏ hơn 20k tokens, xử lý một lần")
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
    api_key = check_environment()

    client = genai.Client(api_key=api_key)
    print("\n--- Môi trường đã sẵn sàng! ---")

    # === TEST PHASE 4: Chunking Support ===
    test_file = os.path.expanduser(
        "/Users/tttv/Library/Mobile Documents/com~apple~CloudDocs/Ebook/Robert Jordan/The Complete Wheel of Time (422)/B1-CH20.md"
    )
    success = process_chapter(client, test_file, voice="Kore")

    if success:
        print("\n🎉 Phase 3 test PASSED!")
    else:
        print("\n❌ Phase 3 test FAILED!")


if __name__ == "__main__":
    main()

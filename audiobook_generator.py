import os
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


def check_environment():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("LỖI: Biến môi trường 'GEMINI_API_KEY' không được tìm thấy.")
        sys.exit(1)

    print("✅ Đã tìm thấy GEMINI_API_KEY.")
    return api_key


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
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()

        print(f"📄 Đã đọc {len(content)} ký tự")

        # Step 4: Generate audio
        print("🎙️  Đang chuyển đổi text thành audio...")
        audio_data = generate_audio_data(client, content, voice=voice)
        print(f"✅ Đã tạo {len(audio_data):,} bytes audio data")

        # Step 5: Save WAV file
        save_wav_file(str(output_path), audio_data)
        print(f"💾 Đã lưu: {output_path}")

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

    # === TEST PHASE 3: File Handling ===
    test_file = os.path.expanduser(
        "/Users/tttv/Library/Mobile Documents/com~apple~CloudDocs/Ebook/Robert Jordan/The Complete Wheel of Time (422)/B1-CH19-mini.md"
    )
    success = process_chapter(client, test_file, voice="Kore")

    if success:
        print("\n🎉 Phase 3 test PASSED!")
    else:
        print("\n❌ Phase 3 test FAILED!")


if __name__ == "__main__":
    main()

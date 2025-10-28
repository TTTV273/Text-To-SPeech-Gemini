import os
import sys
import wave

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


def main():
    print("--- Bắt đầu quá trình tạo sách nói ---")
    api_key = check_environment()

    client = genai.Client(api_key=api_key)
    print("\n--- Môi trường đã sẵn sàng! ---")

    # === TEST PHASE 2: Core TTS Logic ===
    test_text = "Một số người đã nhìn quanh Moiraine khi cô bước ra phòng chung, vài người có ánh mắt thông cảm."
    print(f"\n🎙️  Đang tạo audio cho text: {test_text}")

    try:
        print("⏳ Đang gọi Gemini API...")
        audio_data = generate_audio_data(client, test_text, voice="Kore")
        print(f"✅ Đã nhận được {len(audio_data):,} bytes audio data")

        output_file = "test_output.wav"
        save_wav_file(output_file, audio_data)
        print(f"✅ Đã lưu file: {output_file}")

        file_size = os.path.getsize(output_file)
        print(f"📊 File size: {file_size:,} bytes")

        if file_size < 1000:
            print("⚠️  Cảnh báo: File quá nhỏ, có thể bị lỗi!")
        else:
            print("\n🎉 Phase 2 hoàn thành! Hãy mở file test_output.wav để nghe thử!")

    except Exception as e:
        print(f"\n❌ Lỗi xảy ra: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

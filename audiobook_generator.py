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


def generate_audio_data(client, text, voice="Charon"):
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


if __name__ == "__main__":
    main()

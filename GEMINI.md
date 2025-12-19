# Project Overview

Text-To-Speech-Gemini is a Python-based text-to-speech application using Google's Gemini API with native TTS capabilities. The project leverages Gemini 2.5 models (Flash/Pro Preview TTS) to generate single-speaker and multi-speaker audio from text.

## Core Components

*   **`CLAUDE.md`**: Provides guidance to the Claude Code AI on how to work with the repository. It gives a high-level overview of the project, API integration, implementation patterns, and limitations.
*   **`3.RESOURCES/251028-Speech_generation.md`**: Contains the complete Gemini TTS API documentation, including voice options, supported languages, multi-speaker configuration examples, and style control prompting techniques.
*   **Python Scripts (Not present but inferred from documentation)**: The project is expected to contain Python scripts that use the `google-genai` library to interact with the Gemini API and the `wave` module to save the generated audio to `.wav` files.

## Vai trò và Phương pháp Hợp tác

**Cập nhật quan trọng từ người dùng (2025-10-28):**

Người dùng (anh Vũ) muốn **tự tay viết code và sửa lỗi** để phục vụ cho quá trình học tập và tiến bộ.

Vai trò của `gemini-tts` và `claude-tts` là **cố vấn (advisor)**, không phải là người trực tiếp viết code.

**Nhiệm vụ chính:**
-   **Đưa ra kế hoạch:** Xây dựng các kế hoạch chi tiết.
-   **Phân tích & Đánh giá:** Xem xét code hoặc kế hoạch của người dùng, chỉ ra các vấn đề và đề xuất giải pháp.
-   **Cung cấp mẫu code:** Đưa ra các đoạn code ví dụ (patterns) để minh họa cho giải pháp, thay vì viết toàn bộ file.
-   **Hướng dẫn và giải thích:** Giải thích các khái niệm phức tạp và hướng dẫn cách tiếp cận.

**TUYỆT ĐỐI KHÔNG:**
-   Tự động viết toàn bộ file code khi không được yêu cầu rõ ràng.
-   Tự động sửa lỗi trong code của người dùng. Thay vào đó, hãy chỉ ra lỗi và gợi ý cách sửa.

## Building and Running

### Prerequisites

*   Python
*   `google-genai` library
*   An environment variable named `GEMINI_API_KEY` with a valid Gemini API key.

### Installation

1.  Install the dependencies using a package manager like `uv`:
    ```bash
    uv pip install -r requirements.txt
    ```

### Running the Application

To run scripts in this project, use the virtual environment with `uv`:

```bash
source .venv/bin/activate && uv run <script_name>.py
```

To generate speech, you would run a Python script. The following is an example of how to generate single-speaker audio:

```python
from google import genai
from google.genai import types
import wave

# Set up the wave file to save the output:
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
   with wave.open(filename, "wb") as wf:
      wf.setnchannels(channels)
      wf.setsampwidth(sample_width)
      wf.setframerate(rate)
      wf.writeframes(pcm)

client = genai.Client()

response = client.models.generate_content(
   model="gemini-2.5-flash-preview-tts",
   contents="Say cheerfully: Have a wonderful day!",
   config=types.GenerateContentConfig(
      response_modalities=["AUDIO"],
      speech_config=types.SpeechConfig(
         voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
               voice_name='Kore',
            )
         )
      ),
   )
)

data = response.candidates[0].content.parts[0].inline_data.data

file_name='out.wav'
wave_file(file_name, data) # Saves the file to current directory
```

## Development Conventions

*   The API key should be stored in an environment variable and not committed to git.
*   Use `gemini-2.5-flash-preview-tts` for development and testing, and `gemini-2.5-pro-preview-tts` for production-quality requirements.
*   Test prompts in AI Studio before implementing them in code.
*   Audio data is extracted from `response.candidates[0].content.parts[0].inline_data.data`.
*   The output audio format is PCM (16-bit, 24000 Hz, mono) and should be saved as a `.wav` file.
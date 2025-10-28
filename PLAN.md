# Kế hoạch Xây dựng Script Tạo Sách nói (Audiobook Generator)

Tài liệu này mô tả kế hoạch chi tiết để xây dựng script `audiobook_generator.py` theo các yêu cầu đã được cập nhật.

## 1. Mục tiêu

Xây dựng một script Python cho phép người dùng chỉ định một hoặc nhiều file chương truyện (định dạng Markdown) và tự động chuyển đổi chúng thành các file âm thanh (`.wav`) tương ứng.

## 2. Kiến trúc & Công nghệ

-   **Ngôn ngữ:** Python 3.
-   **Thư viện chính:**
    -   `google-genai`: Để tương tác với Gemini Text-to-Speech API.
    -   `os`, `pathlib`: Để xử lý đường dẫn, tạo thư mục.
    -   `argparse`: Để nhận danh sách file từ dòng lệnh.
    -   `wave`: Để ghi file âm thanh `.wav`.
-   **Model API:** `gemini-2.5-flash-preview-tts`.
-   **Giọng đọc:** Sử dụng một giọng kể chuyện duy nhất, mặc định là `Charon` (giọng đọc tin tức, rõ ràng) để đảm bảo tính nhất quán.

### Lưu ý Kỹ thuật Quan trọng: Khởi tạo Gemini Client

**Bài học rút ra (2025-10-28):** Phiên bản `google-genai` SDK mới (ví dụ: v1.46.0) **KHÔNG** sử dụng hàm `genai.configure(api_key=...)` để cấu hình. Cách làm này đã cũ và sẽ gây ra lỗi `AttributeError`.

**Pattern đúng là khởi tạo một đối tượng `Client`:**

```python
from google import genai

# Sai ❌
# genai.configure(api_key="YOUR_KEY")

# Đúng ✅
client = genai.Client(api_key="YOUR_KEY")

# Sau đó, các lời gọi API sẽ thông qua đối tượng client:
# response = client.models.generate_content(...)
```

Việc này cần được ghi nhớ để áp dụng cho tất cả các hàm gọi API về sau.

## 3. Cấu trúc File của Dự án

```
Text-To-SPeech-Gemini/
├── audiobook_generator.py  # Script chính
├── PLAN.md                 # File kế hoạch này
├── README.md
└── ...
```

## 4. Luồng thực thi chi tiết

Script `audiobook_generator.py` sẽ hoạt động theo các bước sau:

1.  **Nhận Input:** Script được gọi từ terminal với các đường dẫn đến file chapter làm tham số.
    ```bash
    python audiobook_generator.py "/path/to/chapter1.md" "/path/to/chapter2.md"
    ```
2.  **Lặp qua từng file:** Script sẽ xử lý tuần tự từng file được cung cấp.
3.  **Với mỗi file chapter:**
    a.  **Xác định đường dẫn:**
        -   `input_path`: Đường dẫn đến file chapter (ví dụ: `/path/to/book/chapter1.md`).
        -   `parent_dir`: Thư mục cha chứa file chapter (`/path/to/book/`).
        -   `output_dir`: Thư mục `TTS` bên trong thư mục cha (`/path/to/book/TTS/`).
        -   `output_path`: Đường dẫn file âm thanh đầu ra (`/path/to/book/TTS/chapter1.wav`).
    b.  **Tạo thư mục Output:** Kiểm tra nếu `output_dir` chưa tồn tại thì tạo mới.
    c.  **Đọc nội dung:** Đọc toàn bộ nội dung văn bản từ `input_path`.
    d.  **Chia nhỏ văn bản (Chunking):**
        -   Nội dung sẽ được chia thành các đoạn nhỏ (chunks) để không vượt quá giới hạn token của API.
        -   **Chiến lược:** Chia theo các đoạn văn (tách bởi hai dấu xuống dòng `

`). Nếu một đoạn văn vẫn quá dài, sẽ tiếp tục chia nhỏ theo câu.
    e.  **Tạo âm thanh cho từng Chunk:**
        -   Lặp qua danh sách các `text_chunk`.
        -   Với mỗi `chunk`, gọi Gemini TTS API để lấy dữ liệu âm thanh (dạng PCM).
        -   Lưu dữ liệu âm thanh của tất cả các chunk vào một danh sách (list).
    f.  **Nối và Lưu file:**
        -   Nối tất cả dữ liệu âm thanh từ danh sách lại thành một chuỗi bytes duy nhất.
        -   Sử dụng thư viện `wave` để ghi chuỗi bytes này thành một file `.wav` hoàn chỉnh tại `output_path`.
    g.  **Thông báo:** In ra thông báo cho biết đã xử lý xong chapter nào và file được lưu ở đâu.

## 5. Các hàm chính cần xây dựng

-   `main()`:
    -   Thiết lập `argparse` để nhận danh sách file.
    -   Gọi `process_chapter` cho mỗi file.
-   `process_chapter(file_path: str)`:
    -   Thực hiện toàn bộ luồng xử lý cho một chapter (bước 3a đến 3g).
-   `get_text_chunks(text: str, max_chunk_size: int) -> list[str]`:
    -   Chịu trách nhiệm chia nhỏ văn bản.
-   `generate_audio_data(text: str) -> bytes`:
    -   Gọi API và trả về dữ liệu âm thanh thô.
-   `save_wav_file(path: str, audio_data: bytes)`:
    -   Hàm tiện ích để lưu file `.wav` (dựa trên code mẫu của Google).

## 6. Các bước phát triển (Iterative Plan)

1.  **Giai đoạn 1 (Setup):** Tạo file `audiobook_generator.py` với hàm `main` và `argparse` để nhận file. In ra đường dẫn các file nhận được để kiểm tra.
2.  **Giai đoạn 2 (Core TTS Logic):** Viết hàm `generate_audio_data` và `save_wav_file`. Thử nghiệm với một đoạn text ngắn, cứng (hardcoded) để đảm bảo có thể tạo ra file `.wav`.
3.  **Giai đoạn 3 (File Handling):** Viết hàm `process_chapter`. Implement logic đọc file, xác định đường dẫn output và tạo thư mục. Tạm thời chưa có chunking, thử với một file chapter thật ngắn.
4.  **Giai đoạn 4 (Chunking):** Hoàn thiện hàm `get_text_chunks` và tích hợp vào `process_chapter`.
5.  **Giai đoạn 5 (Integration & Refinement):** Tích hợp tất cả các thành phần, thêm xử lý lỗi (ví dụ: file không tồn tại, lỗi API) và các thông báo tiến trình cho người dùng.

---

## 7. Hướng dẫn Chi tiết Từng Giai đoạn

### ✅ Giai đoạn 1: Setup - ĐÃ HOÀN THÀNH

**Mục tiêu đã đạt được:**
- ✅ Tạo file `audiobook_generator.py`
- ✅ Implement hàm `check_environment()` với validation API key
- ✅ Khởi tạo `genai.Client` đúng cách
- ✅ Test chương trình chạy thành công

---

### 🎯 Giai đoạn 2: Core TTS Logic (ĐANG THỰC HIỆN)

**Mục tiêu:** Viết 2 hàm cốt lõi (`generate_audio_data` và `save_wav_file`) và test với text ngắn hardcoded.

#### 📚 Kiến thức nền tảng: WAV File Structure

**Cấu trúc file WAV:**
```
┌─────────────────┐
│ RIFF Header     │ ← 12 bytes: "RIFF", file size, "WAVE"
├─────────────────┤
│ Format Chunk    │ ← 24 bytes: audio specs (sample rate, channels, etc)
├─────────────────┤
│ Data Chunk      │ ← 8 bytes header + PCM audio data
└─────────────────┘
```

**Điểm quan trọng:**
- Gemini API chỉ trả về **raw PCM data** (phần cuối)
- Ta phải tự tạo RIFF Header + Format Chunk bằng thư viện `wave`
- PCM data từ Gemini: 16-bit, 24000 Hz, mono (1 channel)

---

#### 🔨 Bước 2.1: Implement `save_wav_file()`

**Chức năng:** Nhận PCM data và lưu thành file .wav hoàn chỉnh với header đúng chuẩn.

**Code mẫu:**
```python
import wave

def save_wav_file(filename, pcm_data, channels=1, rate=24000, sample_width=2):
    """
    Lưu PCM audio data thành file .wav

    Args:
        filename: Đường dẫn file output (ví dụ: "output.wav")
        pcm_data: Raw PCM bytes từ Gemini API
        channels: Số kênh audio (1 = mono, 2 = stereo)
        rate: Sample rate (Hz) - Gemini dùng 24000
        sample_width: Bytes per sample (2 = 16-bit)
    """
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)      # Mono
        wf.setsampwidth(sample_width)  # 16-bit
        wf.setframerate(rate)          # 24kHz
        wf.writeframes(pcm_data)       # Write PCM data
```

**Giải thích từng dòng:**
- `wave.open(filename, "wb")`: Mở file ở chế độ write binary, tự động tạo WAV header
- `setnchannels(1)`: Mono audio (1 kênh)
- `setsampwidth(2)`: 2 bytes = 16-bit per sample
- `setframerate(24000)`: Sample rate theo spec của Gemini
- `writeframes(pcm_data)`: Ghi raw PCM data vào

---

#### 🔨 Bước 2.2: Implement `generate_audio_data()`

**Chức năng:** Gọi Gemini TTS API để convert text thành audio PCM data.

**Code mẫu:**
```python
from google import genai
from google.genai import types

def generate_audio_data(client, text, voice='Charon'):
    """
    Gọi Gemini TTS API để convert text → audio

    Args:
        client: genai.Client instance
        text: Text cần convert
        voice: Tên giọng đọc (mặc định: Charon)

    Returns:
        bytes: Raw PCM audio data
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],  # ← Bắt buộc phải có!
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    )
                )
            ),
        )
    )

    # Extract PCM data từ response structure
    pcm_data = response.candidates[0].content.parts[0].inline_data.data
    return pcm_data
```

**Giải thích các thành phần:**
- `response_modalities=["AUDIO"]`: Yêu cầu API trả về audio (bắt buộc)
- `speech_config`: Cấu hình giọng đọc
- `voice_name='Charon'`: Giọng tin tức, rõ ràng (có 30 giọng khác trong docs)
- Response structure: `response → candidates[0] → content → parts[0] → inline_data → data`

---

#### 🔨 Bước 2.3: Update `main()` để test

**Thêm vào hàm `main()`:**

```python
def main():
    print("--- Bắt đầu quá trình tạo sách nói ---")
    api_key = check_environment()

    client = genai.Client(api_key=api_key)
    print("\n--- Môi trường đã sẵn sàng! ---")

    # === THÊM PHẦN TEST BÊN DƯỚI ===

    # Test với text ngắn
    test_text = "Hello! This is a test of the Gemini text to speech API."
    print(f"\n🎙️  Đang tạo audio cho text: {test_text}")

    try:
        # Gọi API
        audio_data = generate_audio_data(client, test_text, voice='Charon')
        print(f"✅ Đã nhận được {len(audio_data)} bytes audio data")

        # Lưu file
        output_file = "test_output.wav"
        save_wav_file(output_file, audio_data)
        print(f"✅ Đã lưu file: {output_file}")
        print("\n💡 Hãy mở file test_output.wav để nghe thử!")

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
```

---

#### 📋 Checklist Implementation cho Phase 2

**Bạn cần làm theo thứ tự:**

1. ✅ **Import thêm:** Thêm `import wave` và `from google.genai import types` ở đầu file
2. ✅ **Thêm hàm `save_wav_file()`:** Copy code mẫu vào file (đặt sau hàm `check_environment()`)
3. ✅ **Thêm hàm `generate_audio_data()`:** Copy code mẫu vào file (đặt sau `save_wav_file()`)
4. ✅ **Update hàm `main()`:** Thêm đoạn test code vào cuối hàm
5. ✅ **Chạy test:** `uv run audiobook_generator.py`
6. ✅ **Verify output:** Kiểm tra file `test_output.wav` được tạo
7. ✅ **Nghe thử:** Mở file bằng trình nghe nhạc để verify audio

---

#### 🎓 Key Takeaways cho Phase 2

**Những điểm quan trọng cần nhớ:**
- API call mất 2-5 giây tùy độ dài text → cần patience
- PCM data là binary (bytes), không phải string
- Nếu lỗi `IndexError`: API không trả về candidates → check API key hoặc quota
- WAV header tự động được tạo bởi thư viện `wave` → không cần tạo thủ công
- Response structure có nhiều lớp → cần extract đúng path: `candidates[0].content.parts[0].inline_data.data`

---

#### 🔍 Debugging Tips

**Nếu gặp lỗi:**

1. **Import Error:** Kiểm tra đã import `types` chưa
   ```python
   from google.genai import types  # Cần có dòng này!
   ```

2. **AttributeError:** Kiểm tra lại response structure
   ```python
   # Debug: In ra response để xem cấu trúc
   print(response)
   ```

3. **File không phát được:** Kiểm tra file size
   ```python
   import os
   print(f"File size: {os.path.getsize('test_output.wav')} bytes")
   # Nếu < 1000 bytes → có vấn đề
   ```

---

**Kết quả mong đợi sau Phase 2:**
- ✅ File `test_output.wav` được tạo thành công
- ✅ File có thể phát được và nghe thấy text được đọc bằng giọng Charon
- ✅ Console hiển thị số bytes nhận được từ API
- ✅ Không có error xảy ra

**Sau khi hoàn thành Phase 2, bạn có thể chuyển sang Phase 3: File Handling**

---
---
---

# Phân tích Kỹ thuật & Đánh giá Kế hoạch (từ Claude-TTS)

**Người phân tích:** claude-tts (Code Specialist)
**Ngày:** 2025-10-28
**Trạng thái:** ⚠️ Kế hoạch tốt nhưng cần các cải tiến quan trọng.

---

## 📊 Đánh giá Tổng thể

**Điểm mạnh:** ✅
- Kiến trúc rõ ràng, phân chia hàm tốt.
- Hướng tiếp cận phát triển lặp (5 giai đoạn) rất hay.
- Sử dụng Gemini TTS API đúng theo tài liệu.
- Cấu trúc thư mục output hợp lý.

**Vấn đề Nghiêm trọng:** ⛔
- Thiếu cơ chế đếm token.
- Không có chiến lược xử lý lỗi.
- Không xem xét đến giới hạn tần suất gọi API (rate limiting).
- Chưa xử lý cú pháp Markdown.

---

## 🔴 Các Vấn đề Nghiêm trọng (Bắt buộc phải sửa)

### 1. **Đếm Token - QUAN TRỌNG NHẤT**

**Vấn đề:** Kế hoạch hiện tại chia theo đoạn văn/câu, nhưng API giới hạn 32k **token**, không phải ký tự. Một đoạn văn có thể có 5k ký tự nhưng lại là 7k token.

**Giải pháp:** Cần sử dụng thư viện như `tiktoken` để đếm token chính xác.

**Mẫu code:**
```python
import tiktoken

def count_tokens(text: str, model: str) -> int:
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

# Mỗi chunk nên có tối đa ~20k token để có vùng đệm an toàn.
```

**Trường hợp đặc biệt:** Nếu một câu đơn lẻ dài hơn 32k token? Cần phải chia nhỏ ở cấp độ câu và đưa ra cảnh báo.

---


### 2. **Logic Nối file Âm thanh**

**Vấn đề:** Kế hoạch nói "nối tất cả dữ liệu âm thanh" nhưng chưa làm rõ về đặc thù của định dạng WAV.

**Cấu trúc file WAV:**
`[Header RIFF 44 bytes] [Dữ liệu PCM]`

**Cách tiếp cận đúng:**
- Trích xuất dữ liệu PCM thô (không có header) từ mỗi chunk âm thanh.
- Nối các chuỗi bytes PCM thô lại với nhau.
- Ghi MỘT file WAV duy nhất với một header và toàn bộ dữ liệu PCM đã nối.

---


### 3. **Xử lý Markdown**

**Thiếu sót:** Chưa đề cập đến việc loại bỏ cú pháp Markdown.

**Vấn đề:**
- `# Chapter 1` → TTS sẽ đọc "dấu thăng Chapter 1".
- `**bold text**` → TTS sẽ đọc "sao sao bold text...".

**Giải pháp:** Sử dụng regex hoặc thư viện `markdown-it-py` để làm sạch văn bản trước khi gửi đến API.

**Mẫu code (Regex):**
```python
import re

def clean_markdown(text: str) -> str:
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE) # Headers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text) # Bold
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text) # Links
    return text
```

---


### 4. **Chiến lược Xử lý lỗi**

**Các trường hợp lỗi bị bỏ qua:**
- File không tồn tại.
- Thiếu API key.
- Vượt quá quota API.
- Không có quyền ghi file.

**Yêu cầu:** Sử dụng các khối `try...except` để bắt các lỗi cụ thể và đưa ra thông báo rõ ràng.

---


### 5. **Giới hạn Tần suất gọi API (Rate Limiting)**

**Vấn đề:** Gọi API liên tục cho nhiều chunk có thể bị từ chối dịch vụ (throttling).

**Giải pháp:** Sử dụng thư viện như `tenacity` để tự động thử lại (retry) với khoảng thời gian tăng dần (exponential backoff).

**Mẫu code:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_audio_data(text: str) -> bytes:
    # API call here
    pass
```

---


## ✅ Kế hoạch Phát triển đã được Điều chỉnh (Đề xuất từ Claude-TTS)

**Giai đoạn 1 - Setup & Môi trường:**
- Cài đặt dependencies: `pip install google-genai tiktoken tenacity markdown-it-py`.
- Viết hàm `check_environment` để xác thực API key.
- Test một API call đơn giản.

**Giai đoạn 2 - Xử lý Văn bản:**
- Viết hàm `read_and_clean_markdown` (đọc file UTF-8, làm sạch cú pháp Markdown).
- Viết hàm `count_tokens`.

**Giai đoạn 3 - Logic Chia nhỏ (Chunking):**
- Viết hàm `get_text_chunks` dựa trên số token.
- Viết unit test cho hàm này.

**Giai đoạn 4 - Lõi TTS:**
- Viết hàm `generate_audio_data` có tích hợp retry logic.
- Viết hàm `save_wav_file` xử lý việc nối dữ liệu PCM thô và ghi header một lần.

**Giai đoạn 5 - Tích hợp:**
- Kết hợp tất cả các thành phần trong `process_chapter`.
- Thêm xử lý lỗi đầy đủ và thông báo tiến trình chi tiết.
- Test toàn diện với một file chapter thật.
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

#### 🧪 Testing Strategy: Test trong main() vs Test file riêng

**Câu hỏi quan trọng:** Nên test trong `main()` hay tạo file `test_phase2.py` riêng?

**TL;DR:** Tùy phase của project!

---

##### **Approach 1: Test trong main() (RECOMMENDED cho Phase 2)**

**Khi nào dùng:**
- ✅ Prototype phase / POC (Proof of Concept)
- ✅ Quick experiment để verify API hoạt động
- ✅ Test code đơn giản (< 20 dòng)
- ✅ Sẽ xóa test code sau khi verify OK

**Ưu điểm:**
- Nhanh, đơn giản, 1 file duy nhất
- Dễ debug cho beginners
- Phù hợp learning projects

**Nhược điểm:**
- Main function bloated khi project lớn
- Mix production + test code
- Không reusable

**Code example:**
```python
def main():
    # ... setup code ...

    # === TEST PHASE 2 (sẽ xóa sau) ===
    test_text = "Hello test"
    audio_data = generate_audio_data(client, test_text)
    save_wav_file("test_output.wav", audio_data)
    # === END TEST ===
```

**Cleanup sau Phase 2:**
Sau khi verify `test_output.wav` phát được → **Xóa toàn bộ phần TEST** → Giữ main() clean cho Phase 3.

---

##### **Approach 2: Test file riêng (RECOMMENDED cho Phase 3+)**

**Khi nào dùng:**
- ✅ Production code
- ✅ Cần test nhiều scenarios
- ✅ Professional projects
- ✅ Team collaboration

**Cấu trúc file:**
```
Text-To-Speech-Gemini/
├── audiobook_generator.py     # Production (clean!)
├── test_phase2.py              # Test Phase 2
├── test_phase3.py              # Test Phase 3
└── tests/                      # Unit tests (advanced)
    └── test_save_wav.py
```

**Code example - test_phase2.py:**
```python
"""Test Phase 2: Core TTS Logic"""
from audiobook_generator import generate_audio_data, save_wav_file
from google import genai
import os

def test_tts_basic():
    print("=== TEST PHASE 2 ===")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    test_text = "Hello! This is a test."

    try:
        # Test generate_audio_data()
        audio_data = generate_audio_data(client, test_text)
        print(f"✅ Generated {len(audio_data)} bytes")

        # Test save_wav_file()
        save_wav_file("test_output.wav", audio_data)
        print("✅ Saved test_output.wav")

        # Verify
        file_size = os.path.getsize("test_output.wav")
        if file_size > 1000:
            print("🎉 Phase 2 PASSED!")
        else:
            print("⚠️  Warning: File too small")

    except Exception as e:
        print(f"❌ FAILED: {e}")

if __name__ == "__main__":
    test_tts_basic()
```

**Chạy test:**
```bash
uv run test_phase2.py           # Test
uv run audiobook_generator.py   # Production
```

**Ưu điểm:**
- Separation of concerns
- Production code sạch sẽ
- Dễ maintain và mở rộng
- Professional practice

---

##### **📋 Decision Guide**

| Phase | Approach | Lý do |
|-------|----------|-------|
| Phase 1-2 | Test trong main() | Prototype, quick validation |
| Phase 3+ | Test file riêng | Production-ready code |
| Final | Unit tests (pytest) | Professional quality |

**Recommendation cho project này:**
1. **Phase 2:** Test trong main() (quick & dirty)
2. **Sau Phase 2:** Xóa test code, cleanup main()
3. **Phase 3+:** Tạo test files riêng nếu cần

---

**Kết quả mong đợi sau Phase 2:**
- ✅ File `test_output.wav` được tạo thành công
- ✅ File có thể phát được và nghe thấy text được đọc bằng giọng Charon
- ✅ Console hiển thị số bytes nhận được từ API
- ✅ Không có error xảy ra

**Sau khi hoàn thành Phase 2, bạn có thể chuyển sang Phase 3: File Handling**

---

### 🎯 Giai đoạn 3: File Handling (ĐANG THỰC HIỆN)

**Mục tiêu:** Xử lý file Markdown từ đường dẫn thực tế, tạo output directory và lưu file WAV.

**Giới hạn Phase 3:**
- ⚠️ **CHƯA có chunking** - chỉ xử lý file ngắn (< 32k tokens)
- ⚠️ **CHƯA có argparse** - hardcode test path trong main() để verify
- ⚠️ **CHƯA có markdown cleaning** - assume text đã clean

---

#### 📚 Requirements Phase 3

**Input:**
- User chỉ định đường dẫn file chapter (ví dụ: `/path/to/chapter1.md`)

**Process Flow:**
1. Đọc nội dung text từ file (UTF-8 encoding)
2. Parse paths: `parent_dir`, `output_dir`, `output_filename`
3. Tạo thư mục `TTS` nếu chưa tồn tại
4. Convert text → audio (reuse `generate_audio_data()`)
5. Lưu file WAV với tên matching input

**Output:**
- File `.wav` trong thư mục `TTS` subfolder
- Example: `/path/to/book/chapter1.md` → `/path/to/book/TTS/chapter1.wav`

---

#### 🔨 Bước 3.1: Thêm import `pathlib`

**Tại sao dùng pathlib?**
- Object-oriented path handling
- Cross-platform (Windows, Linux, Mac)
- Elegant syntax với `/` operator
- Built-in methods: `.parent`, `.stem`, `.mkdir()`, etc.

**Code:**
```python
from pathlib import Path  # Thêm sau import wave
```

**So sánh với os.path:**
```python
# Old way (os.path)
parent_dir = os.path.dirname(file_path)
output_dir = os.path.join(parent_dir, "TTS")
filename = os.path.splitext(os.path.basename(file_path))[0]

# New way (pathlib) - BETTER!
input_path = Path(file_path)
parent_dir = input_path.parent
output_dir = parent_dir / "TTS"
filename = input_path.stem
```

---

#### 🔨 Bước 3.2: Implement `process_chapter()`

**Function signature:**
```python
def process_chapter(client, file_path, voice="Kore"):
    """
    Xử lý một chapter: đọc file → convert → save audio

    Args:
        client: genai.Client instance
        file_path: Đường dẫn đến file .md
        voice: Giọng đọc (default: Kore)

    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
```

**Implementation:**
```python
def process_chapter(client, file_path, voice="Kore"):
    try:
        # Step 1: Parse paths
        input_path = Path(file_path)
        parent_dir = input_path.parent
        output_dir = parent_dir / "TTS"
        output_filename = input_path.stem + ".wav"  # chapter1.md → chapter1.wav
        output_path = output_dir / output_filename

        print(f"\n📖 Đang xử lý: {input_path.name}")

        # Step 2: Create output directory
        output_dir.mkdir(exist_ok=True)  # exist_ok=True: không lỗi nếu đã tồn tại
        print(f"📁 Output directory: {output_dir}")

        # Step 3: Read file content
        with open(input_path, 'r', encoding='utf-8') as f:  # UTF-8 cho tiếng Việt!
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
```

---

#### 📖 Key Points Giải thích

**1. Path handling với pathlib:**
```python
input_path = Path(file_path)
parent_dir = input_path.parent       # /path/to/book/chapter1.md → /path/to/book
output_dir = parent_dir / "TTS"      # /path/to/book + TTS → /path/to/book/TTS
```

**2. Filename conversion:**
```python
output_filename = input_path.stem + ".wav"
# chapter1.md → stem="chapter1" → "chapter1.wav"
# prologue.md → stem="prologue" → "prologue.wav"
```

**3. Safe directory creation:**
```python
output_dir.mkdir(exist_ok=True)
# exist_ok=True: Không raise exception nếu folder đã tồn tại
# Tự động tạo nếu chưa có
```

**4. UTF-8 encoding (CRITICAL!):**
```python
with open(input_path, 'r', encoding='utf-8') as f:
```
- Mặc định Python có thể dùng encoding khác → lỗi với tiếng Việt
- `encoding='utf-8'` đảm bảo đọc đúng dấu tiếng Việt

**5. Error handling layers:**
```python
except FileNotFoundError:        # Specific error → clear message
except Exception as e:           # Catch-all → detailed traceback
```

---

#### 🔨 Bước 3.3: Test với file thật

**Chuẩn bị test file:**
1. Tạo một file test ngắn (< 500 từ) với content Wheel of Time
2. Đặt ở vị trí nào đó (ví dụ: `/Users/tttv/test_chapter.md`)

**Update `main()` để test:**
```python
def main():
    print("--- Bắt đầu quá trình tạo sách nói ---")
    api_key = check_environment()

    client = genai.Client(api_key=api_key)
    print("\n--- Môi trường đã sẵn sàng! ---")

    # === TEST PHASE 3: File Handling ===
    test_file = "/path/to/your/test_chapter.md"  # ← Thay đường dẫn thật

    success = process_chapter(client, test_file, voice="Kore")

    if success:
        print("\n✅ Phase 3 test PASSED!")
    else:
        print("\n❌ Phase 3 test FAILED!")
```

**Expected output:**
```
--- Bắt đầu quá trình tạo sách nói ---
✅ Đã tìm thấy GEMINI_API_KEY.

--- Môi trường đã sẵn sàng! ---

📖 Đang xử lý: test_chapter.md
📁 Output directory: /path/to/your/TTS
📄 Đã đọc 1,234 ký tự
🎙️  Đang chuyển đổi text thành audio...
✅ Đã tạo 150,328 bytes audio data
💾 Đã lưu: /path/to/your/TTS/test_chapter.wav

✅ Phase 3 test PASSED!
```

---

#### 🎓 Key Takeaways Phase 3

**Kỹ năng đã học:**
- ✅ Path manipulation với `pathlib` (modern Python)
- ✅ File I/O với proper encoding (UTF-8)
- ✅ Directory creation safety (`exist_ok=True`)
- ✅ Error handling với specific exceptions
- ✅ Function composition (reuse existing functions)
- ✅ User experience với progress messages

**Design patterns:**
- ✅ Single Responsibility: `process_chapter()` orchestrates, không duplicate logic
- ✅ DRY: Reuse `generate_audio_data()` và `save_wav_file()`
- ✅ Fail-safe: Return boolean để caller biết success/failure

---

**Kết quả mong đợi sau Phase 3:**
- ✅ File WAV được tạo trong thư mục `TTS` subfolder
- ✅ Filename matches input (chapter1.md → chapter1.wav)
- ✅ UTF-8 content đọc đúng (Vietnamese text OK)
- ✅ Directory tự động tạo nếu chưa tồn tại
- ✅ Error handling graceful

**Giới hạn hiện tại (sẽ fix ở Phase 4):**
- ⚠️ Chỉ xử lý được file ngắn (< 32k tokens)
- ⚠️ Không có chunking cho file dài
- ⚠️ Chưa clean markdown syntax
- ⚠️ Chưa có CLI interface (argparse)

**Sau khi hoàn thành Phase 3, bạn có thể chuyển sang Phase 4: Chunking**

---

### 🎯 Giai đoạn 4: Chunking & Processing file dài (ĐANG THỰC HIỆN)

**Mục tiêu:** Nâng cấp `process_chapter` để xử lý các file chapter có dung lượng lớn hơn 32k token một cách an toàn.

**Yêu cầu:**
- ✅ Làm sạch cú pháp Markdown từ text đầu vào
- ✅ Implement logic chia văn bản (đã làm sạch) thành các `chunk` nhỏ hơn giới hạn token
- ✅ Nối dữ liệu audio từ các `chunk` lại thành một file WAV duy nhất

**Dependencies cần install:**
```bash
uv add tiktoken
```

---

#### 📚 Kiến thức nền tảng: Chunking Strategy

**Vấn đề:** Một chapter có thể dài 10,000 từ (~13k token), nhưng cũng có thể dài 50,000 từ (~65k token), vượt xa giới hạn 32k token của API.

**Giải pháp (Greedy Algorithm):**
1.  **Clean:** Làm sạch toàn bộ cú pháp Markdown để có text thuần
2.  **Count:** Đếm tokens (không phải ký tự!) của text
3.  **Split:** Tách text thành các đơn vị ngữ nghĩa (semantic units) - ưu tiên đoạn văn (tách bởi `\n\n`)
4.  **Pack:** Lần lượt thêm từng đơn vị vào một `chunk` hiện tại, vừa thêm vừa đếm token
5.  **Finalize Chunk:** Nếu việc thêm đơn vị tiếp theo làm `chunk` vượt quá giới hạn (20,000 token), thì đóng `chunk` hiện tại lại
6.  **New Chunk:** Bắt đầu một `chunk` mới với đơn vị vừa không thêm được
7.  **Repeat:** Lặp lại cho đến khi hết các đơn vị

**Tại sao không chia theo ký tự?** Vì sẽ cắt đứt giữa chừng một từ, làm cho giọng đọc bị ngắt quãng, thiếu tự nhiên.

**Tại sao max_tokens = 20k thay vì 32k?** Để có buffer an toàn, tránh edge cases khi token count không chính xác 100%.

---

#### 🔨 Bước 4.1: Install dependencies

**Chạy lệnh:**
```bash
uv add tiktoken
```

**Verify installation:**
```python
import tiktoken
print(tiktoken.list_encoding_names())
# Output: ['gpt2', 'r50k_base', 'p50k_base', 'cl100k_base', ...]
```

---

#### 🔨 Bước 4.2: Implement `clean_markdown()`

**Chức năng:** Loại bỏ cú pháp Markdown, trả về plain text.

**⚠️ IMPORTANT:** Không dùng `markdown-it-py` vì nó render ra HTML, không phải plain text!

**Code mẫu (Regex approach - Simple & Reliable):**
```python
import re

def clean_markdown(text: str) -> str:
    """
    Remove Markdown syntax từ text

    Args:
        text: Raw markdown text

    Returns:
        str: Plain text without markdown syntax
    """
    # Headers: # Title → Title
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

    # Bold: **text** → text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

    # Italic: *text* → text
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Links: [text](url) → text (keep text, remove URL)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Code blocks: ```code``` → (remove completely)
    text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)

    # Inline code: `code` → code
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Images: ![alt](url) → (remove completely)
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)

    return text
```

**Test example:**
```python
markdown = """
# Chapter 1

This is **bold** and *italic* text.
Here's a [link](http://example.com).
And `inline code`.
"""

clean_text = clean_markdown(markdown)
# Output: "Chapter 1\n\nThis is bold and italic text.\nHere's a link.\nAnd inline code."
```

---

#### 🔨 Bước 4.3: Implement token counting

**Setup global encoding:**
```python
import tiktoken

# Use GPT-4 encoding (best approximation for Gemini)
ENCODING = tiktoken.get_encoding("cl100k_base")
```

**Implement count function:**
```python
def count_tokens(text: str) -> int:
    """
    Count tokens trong text

    Args:
        text: Input text

    Returns:
        int: Number of tokens
    """
    return len(ENCODING.encode(text))
```

**Example:**
```python
text = "Hello world! This is a test."
tokens = count_tokens(text)
print(f"{len(text)} chars = {tokens} tokens")
# Output: "29 chars = 8 tokens"
```

**Why not just count characters?**
```python
# English: 1 word ≈ 1.3 tokens
"Hello world" → 3 tokens (2 words)

# Vietnamese: 1 word ≈ 2-3 tokens (due to encoding)
"Xin chào" → 5 tokens (2 words)

# Special chars: More tokens
"🎉🎊🎈" → 9 tokens (3 chars!)
```

---

#### 🔨 Bước 4.4: Implement `split_into_chunks()`

**Function signature:**
```python
def split_into_chunks(text: str, max_tokens: int = 20000) -> list[str]:
    """
    Split text thành chunks theo token limit

    Args:
        text: Plain text (đã clean markdown)
        max_tokens: Max tokens per chunk (default: 20k, buffer cho 32k limit)

    Returns:
        list[str]: List of text chunks
    """
```

**Implementation:**
```python
def split_into_chunks(text: str, max_tokens: int = 20000) -> list[str]:
    """Split text into token-safe chunks"""
    chunks = []
    current_chunk = []
    current_token_count = 0

    # Split by paragraphs (double newline)
    paragraphs = text.split('\n\n')

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
                chunks.append('\n\n'.join(current_chunk))

            # Start new chunk with this paragraph
            current_chunk = [para]
            current_token_count = para_tokens
        else:
            # Add to current chunk
            current_chunk.append(para)
            current_token_count += para_tokens

    # Add final chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks
```

**Explanation:**
- Split by `\n\n` (paragraphs) to maintain semantic units
- Track token count, NOT character count
- Use `\n\n`.join() to preserve paragraph breaks in chunks

**Edge case handling:**
```python
# What if single paragraph > 20k tokens?
# Solution: Split by sentences
if para_tokens > max_tokens:
    sentences = para.split('. ')
    # Apply same chunking logic to sentences
```

---

#### 🔨 Bước 4.5: Update `process_chapter()`

**Full updated implementation:**
```python
def process_chapter(client, file_path, voice="Kore"):
    """
    Process a chapter with chunking support

    Args:
        client: genai.Client instance
        file_path: Path to .md file
        voice: Voice name

    Returns:
        bool: Success status
    """
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

        # Step 3: Read and clean file content
        print("📄 Đang đọc file...")
        with open(input_path, 'r', encoding='utf-8') as f:
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
        print(f"📊 Tổng dung lượng: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)")

        # Step 6: Concatenate all audio parts
        print("🔗 Đang nối các phần audio...")
        final_audio_data = b''.join(all_audio_parts)

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
```

**Key changes from Phase 3:**
1. Added markdown cleaning step
2. Added token counting
3. Added chunking logic
4. Loop through chunks for audio generation
5. Concatenate all audio parts
6. Better progress messages

---

#### 📋 Checklist Implementation cho Phase 4

**Anh cần làm theo thứ tự:**

1. ✅ **Install tiktoken:** `uv add tiktoken`
2. ✅ **Import thêm:** Thêm `import re` và `import tiktoken` ở đầu file
3. ✅ **Setup encoding:** Thêm global constant `ENCODING = tiktoken.get_encoding("cl100k_base")`
4. ✅ **Thêm `clean_markdown()`:** Copy function vào file (sau imports)
5. ✅ **Thêm `count_tokens()`:** Copy function vào file (sau `clean_markdown()`)
6. ✅ **Thêm `split_into_chunks()`:** Copy function vào file (sau `count_tokens()`)
7. ✅ **Update `process_chapter()`:** Replace toàn bộ function với version mới
8. ✅ **Test với file:** Chạy với file WoT đã có
9. ✅ **Verify output:** Check TTS folder có file WAV mới

---

#### 🎓 Key Takeaways Phase 4

**Kỹ năng đã học:**
- ✅ **Regex mastery:** Clean Markdown syntax với regex patterns
- ✅ **Token counting:** Understand tokens vs characters (critical!)
- ✅ **Chunking algorithm:** Greedy packing với semantic units
- ✅ **Audio concatenation:** Binary data manipulation (bytes)
- ✅ **Progress tracking:** UX for long-running operations

**Important concepts:**
- 🔑 **Tokens ≠ Characters:** 1 char có thể = 3 tokens (emoji), 1 word có thể = 1-3 tokens
- 🔑 **Buffer safety:** 20k max thay vì 32k để có margin of error
- 🔑 **Semantic chunking:** Chia theo paragraphs, không phải characters
- 🔑 **PCM concatenation:** `b''.join()` works vì PCM là raw audio data
- 🔑 **WAV header magic:** Chỉ cần 1 header cho toàn bộ concatenated audio

**Design patterns:**
- ✅ **Separation of concerns:** Clean → Count → Split → Generate → Concat
- ✅ **Fail-safe:** Token counting prevents API errors
- ✅ **User feedback:** Progress messages every step
- ✅ **Composability:** Reuse existing `generate_audio_data()` and `save_wav_file()`

---

**Kết quả mong đợi sau Phase 4:**
- ✅ Xử lý được file chapter dài (50k+ chars, 65k+ tokens)
- ✅ Auto-split thành multiple chunks khi cần
- ✅ Markdown syntax được clean hoàn toàn
- ✅ Audio từ chunks được nối seamlessly
- ✅ Progress messages rõ ràng cho từng chunk
- ✅ File WAV output quality không đổi (vẫn 24kHz, 16-bit, mono)

**Test scenarios:**
- ✅ File ngắn (< 20k tokens): 1 chunk, xử lý trực tiếp
- ✅ File trung bình (20k-40k tokens): 2 chunks
- ✅ File dài (40k-60k tokens): 3+ chunks
- ✅ File có markdown: Headers, bold, italic, links được clean

**Giới hạn hiện tại (sẽ handle ở Phase 5):**
- ⚠️ Chưa có CLI interface (argparse)
- ⚠️ Chưa có batch processing (multiple files)
- ⚠️ Chưa có skip existing files
- ⚠️ Chưa có resume capability

**Sau khi hoàn thành Phase 4, bạn có thể chuyển sang Phase 5: Integration & Polish**

---

### 🐛 Bug Fix: Missing Audio Content (Phát hiện 2025-10-29)

**Triệu chứng:**
- Audio file được tạo thành công với size lớn (28 MB)
- Token count chính xác (8,816 tokens)
- Nhưng audio bị thiếu một đoạn lớn content ở giữa (~40-50% nội dung)
- Audio "nhảy" từ đoạn này sang đoạn khác

**Ví dụ cụ thể với B1-CH20.md:**
- Đọc đến: "Trong một khoảnh khắc, anh gần như có thể tin rằng cô ta thực sự là Aes Sedai."
- Lập tức nhảy đến: "Anh đã từng thấy những Aes Sedai thấp hơn thống trị..."
- Bị thiếu: 47 dòng content ở giữa (từ dòng 42-88)

---

#### 🔍 Root Cause Analysis

**Giả thuyết chính:** Gemini API trả về audio trong **NHIỀU parts** nhưng code chỉ extract `parts[0]`.

**Bằng chứng:**
```python
# Code hiện tại (dòng 121 trong audiobook_generator.py)
pcm_data = response.candidates[0].content.parts[0].inline_data.data
#                                          ^^^^^^^ CHỈ LẤY PART ĐẦU TIÊN!
```

**Lý do:**
- Gemini TTS có thể chia long text thành multiple audio segments
- Mỗi segment = 1 part trong `response.candidates[0].content.parts[]`
- Nếu có 3 parts nhưng ta chỉ lấy parts[0] → mất 2/3 audio!

**Tại sao không phải lỗi khác:**
- ✅ `clean_markdown()` hoạt động đúng (verified: text còn đầy đủ)
- ✅ Token counting chính xác (8,816 tokens = đúng)
- ✅ File đọc đầy đủ (17,618 chars = full content)
- ✅ Audio concatenation logic đúng (b''.join() works)

---

#### 🔧 Solution: Extract ALL Audio Parts

**Cần update function `generate_audio_data()` (dòng 104-122):**

**Code mới:**
```python
# TODO(human): Handle multiple audio parts
def generate_audio_data(client, text, voice="Kore"):
    """
    Gọi Gemini TTS API để convert text → audio

    Args:
        client: genai.Client instance
        text: Text cần convert
        voice: Giọng đọc (default: Kore)

    Returns:
        bytes: Raw PCM audio data (concatenated from all parts)
    """
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
        if hasattr(part, 'inline_data') and part.inline_data:
            audio_data = part.inline_data.data
            all_audio_parts.append(audio_data)
            print(f"      Part {i}: {len(audio_data):,} bytes")
        else:
            print(f"      Part {i}: No audio data (text part?)")

    if len(all_audio_parts) == 0:
        raise ValueError("No audio data found in API response!")

    # Concatenate all parts
    final_audio = b''.join(all_audio_parts)
    print(f"   ✅ Tổng audio: {len(final_audio):,} bytes")

    return final_audio
```

---

#### 📋 Implementation Checklist

**Anh cần làm:**

1. ✅ **Backup code hiện tại:**
   ```bash
   cp audiobook_generator.py audiobook_generator.py.backup
   ```

2. ✅ **Update `generate_audio_data()`:**
   - Replace function (dòng 104-122) bằng version mới ở trên
   - Thêm logic loop qua ALL parts
   - Thêm debug logging (số parts, size từng part)

3. ✅ **Test với file đã bị lỗi:**
   ```bash
   # Delete file bị lỗi
   rm "/Users/tttv/Library/Mobile Documents/com~apple~CloudDocs/Ebook/Robert Jordan/The Complete Wheel of Time (422)/TTS/B1-CH20.wav"

   # Regenerate
   uv run audiobook_generator.py
   ```

4. ✅ **Verify fix:**
   - Check console output: Có hiển thị "API trả về X parts" không?
   - Check audio duration: Có dài hơn version cũ không?
   - Nghe audio: Content có đầy đủ không?
   - So sánh với text: Audio có match full 17,618 chars không?

---

#### 🎓 Key Learnings

**Bài học quan trọng:**
1. **Never assume API response structure** - Always inspect actual response
2. **Test with various content lengths** - Short vs long text may behave differently
3. **Debug logging is critical** - Print intermediate values để catch issues early
4. **Validate output** - Don't just check file size, verify actual content

**API Response Structure:**
```
response
└── candidates[0]
    └── content
        └── parts[]  ← THIS IS AN ARRAY!
            ├── parts[0].inline_data.data  ← Audio segment 1
            ├── parts[1].inline_data.data  ← Audio segment 2
            └── parts[2].inline_data.data  ← Audio segment 3
```

**Tại sao API chia thành multiple parts:**
- Internal processing limits
- Streaming optimization
- Better error recovery
- Quality control per segment

---

#### 🧪 Expected Results After Fix

**Console output:**
```
🎙️  Đang xử lý chunk 1/1...
   Chunk size: 8,816 tokens
   📦 API trả về 3 parts
      Part 1: 10,234,567 bytes
      Part 2: 9,876,543 bytes
      Part 3: 9,476,616 bytes
   ✅ Tổng audio: 29,587,726 bytes
   ✅ Chunk 1 hoàn thành: 29,587,726 bytes
```

**Audio verification:**
- Duration: ~10-12 minutes (for 8,816 tokens)
- Content: Full chapter từ đầu đến cuối
- No gaps or jumps

---


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
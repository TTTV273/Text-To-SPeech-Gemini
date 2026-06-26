# Báo cáo Tổng kết Triển khai OmniVoice TTS trên Linux Xeon E5-2670

## Tóm tắt điều hành

Dựa trên hai báo cáo nghiên cứu `260625-GEMINI-Deep-Research.md` và `260625-OpenAI-deep-research-report.md`, hệ thống đã được triển khai theo hướng **CPU-first**, bỏ hoàn toàn CUDA/Quadro K4000, dùng môi trường Python riêng, thread tuning, NUMA pinning, checkpoint/resume, parallel chunk workers, và thử nghiệm OpenVINO FP32/W8A8.

Kết luận thực nghiệm quan trọng nhất: **máy Xeon E5-2670 chạy được OmniVoice local ổn định, nhưng không đạt tốc độ real-time**. OpenVINO/W8A8 giảm kích thước model nhưng không tăng tốc trên Sandy Bridge vì CPU chỉ có AVX đời đầu, không có AVX2, AVX-512 VNNI hoặc AMX. Tối ưu thực dụng nhất hiện tại là **PyTorch CPU FP32 + num-step 16 + 4 worker process NUMA-pinned + checkpoint từng chunk**.

Lệnh vận hành mặc định hiện tại:

```bash
ov /path/to/chapter.md --resume
```

Mặc định Linux hiện tại:

```text
device: cpu
dtype: float32
num-step: 16
parallel chunks: 4 workers
NUMA pinning: worker 0/2 -> node 0, worker 1/3 -> node 1
checkpoint: update JSON sau từng chunk với file lock
```

## Những mục đã triển khai so với nghiên cứu

### 1. Bỏ GPU Kepler, đi CPU-first

Hai báo cáo đều kết luận Quadro K4000 không phù hợp cho OmniVoice vì:

- Compute Capability 3.0 quá cũ cho PyTorch hiện đại.
- VRAM 3GB không đủ cho OmniVoice.
- CUDA/PyTorch stack mới không còn support Kepler thực tế.

Triển khai hiện tại đã đi đúng hướng này:

- Không dùng CUDA.
- Không cố revive CUDA 10.x/old PyTorch.
- Default Linux là `cpu + float32`.
- Có cảnh báo nếu ép dtype không phù hợp trên CPU.

### 2. Tách khỏi Python 3.14 hệ thống

Báo cáo OpenAI khuyến nghị Python 3.12/3.13; báo cáo Gemini khuyến nghị pyenv/Python ổn định để tránh rolling-release Arch làm hỏng dependency ML.

Đã triển khai:

- Cài `pyenv` local trong `$HOME`.
- Build Python `3.12.11`.
- Tạo `.venv-omnivoice`.
- Cài PyTorch CPU-only wheel:

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

- Cài OmniVoice và dependency qua `requirements-omnivoice-linux.txt`.
- Không dùng Python hệ thống `3.14.3` cho OmniVoice.

### 3. Tạo Linux launcher riêng, không phá Mac

Yêu cầu thực tế là giữ `omnivoice_generator.py` cho máy Mac/MPS và tạo đường Linux riêng.

Đã thêm:

- `omnivoice_linux_generator.py`
- `ov-linux`
- global symlink `ov` trên máy Linux trỏ tới `ov-linux`
- `ov-numa`
- `batch-numa`
- `ov-openvino`
- `ov-openvino-numa`

Kết quả: trên Linux chỉ cần chạy:

```bash
ov chapter.md --resume
```

Trong repo vẫn giữ launcher Mac cũ.

### 4. PyTorch CPU thread tuning

Báo cáo OpenAI khuyến nghị benchmark 8/16/32 threads và dùng:

- `torch.set_num_threads()`
- `torch.set_num_interop_threads(1)`
- `OMP_NUM_THREADS`
- `MKL_NUM_THREADS`

Đã triển khai:

- `--torch-threads`
- `--torch-interop-threads`
- `torch.set_num_threads()` trước khi load model.
- `torch.set_num_interop_threads(1)`.
- Wrapper set `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OMP_PROC_BIND`, `OMP_PLACES`.

Kết quả benchmark trên `test_short.md`, `num-step 50`:

| Mode | Wall time | Ghi chú |
|------|-----------|---------|
| 16 threads single process | 232s | Tốt nhất trong single-process |
| 32 threads single process | 326s | Chậm hơn do SMT/oversubscription |
| 8 threads NUMA single node | 327s | Ít parallelism hơn |

Kết luận: single-process tối ưu khoảng 16 threads; 32 threads trong một process không hiệu quả.

### 5. NUMA pinning

Báo cáo Gemini nhấn mạnh tránh cross-socket traffic qua QPI; báo cáo OpenAI khuyến nghị `numactl --cpunodebind --membind`.

Đã triển khai:

- Cài `numactl`.
- Xác nhận topology:
  - Node 0: CPU `0-7,16-23`, ~16GB RAM
  - Node 1: CPU `8-15,24-31`, ~16GB RAM
- Tạo `ov-numa` và `ov-openvino-numa`.
- Parallel workers pin round-robin qua 2 NUMA nodes.

### 6. Parallel theo chunk trong cùng file

Báo cáo OpenAI khuyến nghị coarse-grained parallelism theo chapter/segment. Triển khai hiện tại đi xa hơn: song song theo chunk trong cùng một file dài.

Đã triển khai:

- `--parallel-chunks` trong `omnivoice_linux_generator.py`.
- Default hiện tại: `--parallel-chunks 4 --torch-threads 32`.
- Parent process chia chunks round-robin cho workers.
- Worker subprocess chạy qua `numactl`.
- Worker load model một lần, generate nhiều chunks được giao, ghi WAV tạm.
- Parent merge WAV đúng thứ tự và convert MP3.

Ví dụ phân phối workers:

```text
Worker 0 -> NUMA node 0 -> chunks 1,5,9,...
Worker 1 -> NUMA node 1 -> chunks 2,6,10,...
Worker 2 -> NUMA node 0 -> chunks 3,7,11,...
Worker 3 -> NUMA node 1 -> chunks 4,8,12,...
```

Kết quả thực tế với `B6-CH11.md`:

- Input: 13,604 tokens.
- Chunks: 29.
- Output: `B6-CH11.mp3`.
- Duration audio: 27m14s.
- Format: MP3, 24kHz mono.

### 7. Checkpoint/resume an toàn theo chunk

Vấn đề phát hiện trong quá trình chạy: nếu worker bị kill/timeout, chunks WAV có thể đã xong nhưng checkpoint JSON chưa cập nhật đủ.

Đã sửa:

- Parent tạo checkpoint trước khi spawn workers.
- Mỗi worker update `.checkpoint_*.json` ngay sau khi xong từng chunk.
- Dùng `fcntl.flock()` để nhiều worker không ghi đè checkpoint lẫn nhau.
- Khi thành công, xóa cả checkpoint và lock file.

Kết quả: nếu quá trình bị interrupt, chỉ cần chạy lại:

```bash
ov chapter.md --resume
```

Không cần scan tay các `.chunk_*.wav` nữa.

### 8. Giảm num-step từ 50 xuống 16

Báo cáo Gemini có đề cập `num_step=16` là cách tăng tốc đáng kể với hy sinh chất lượng nhỏ. Ban đầu giữ 50 để bảo toàn chất lượng, nhưng benchmark cho thấy quá chậm.

Đã đổi default Linux thành `num-step 16`.

Benchmark `test_short.md`:

| num-step | Wall time | RTF xấp xỉ |
|----------|-----------|------------|
| 50 | 232s | ~51 |
| 16 | 97s | ~21 |

Tăng tốc khoảng 2.4x. Chất lượng nghe thực tế chấp nhận được với audiobook.

### 9. OpenVINO FP32 và W8A8

Báo cáo Gemini kỳ vọng OpenVINO W8A8 là hướng tối ưu chính. Đã triển khai đầy đủ Phase 2 để kiểm chứng.

Đã thêm:

- `scripts/convert_omnivoice_openvino.py`
- `scripts/quantize_omnivoice_openvino.py`
- `omnivoice_openvino_generator.py`
- `ov-openvino`
- `ov-openvino-numa`
- `requirements-openvino.txt`

Chi tiết kỹ thuật:

- Convert full forward path: embeddings + Qwen3 LLM + audio_heads.
- Dùng `attn_implementation="eager"` và `use_cache=False` để OpenVINO trace được graph.
- NNCF W8A8 PTQ với calibration từ pipeline thật.

Kích thước model:

| Model | Size |
|-------|------|
| OpenVINO FP32 IR | ~1.2GB |
| OpenVINO W8A8 IR | ~587MB |

Benchmark `test_short.md`, `num-step 50`, 16 threads:

| Backend | Wall time | RTF xấp xỉ |
|---------|-----------|------------|
| PyTorch FP32 | 232s | ~51 |
| OpenVINO FP32 | 237s | ~52 |
| OpenVINO W8A8 | 236s | ~52 |

Kết luận: OpenVINO/W8A8 giảm memory footprint nhưng không tăng tốc trên Xeon E5-2670.

## Những kỳ vọng không đạt

### OpenVINO W8A8 không nhanh hơn PyTorch

Báo cáo Gemini kỳ vọng W8A8 đạt RTF < 1.0. Trên phần cứng thực tế này, kết quả không đạt.

Nguyên nhân kỹ thuật:

- Xeon E5-2670 là Sandy Bridge-EP, chỉ có AVX đời đầu.
- Không có AVX2.
- Không có AVX-512 VNNI.
- Không có AMX.
- INT8 matrix multiply không có đường phần cứng nhanh như CPU Intel đời mới.

Do đó, W8A8 chỉ giảm dung lượng model, không giảm thời gian inference đáng kể.

### ONNX INT8-HQ chưa triển khai

Báo cáo Gemini nhắc tới `ct03/omnivoice-onnx-int8hq`. Chưa triển khai vì:

- OpenVINO được hai báo cáo xếp cao hơn cho CPU Intel.
- Kết quả OpenVINO đã cho thấy giới hạn chính nằm ở ISA phần cứng, không chỉ engine.
- ONNX có thể vẫn đáng thử, nhưng kỳ vọng tăng tốc thấp trên AVX-only.

### Sherpa-ONNX/C++ chưa triển khai

Báo cáo Gemini xem Sherpa-ONNX/C++ là hướng tương lai. Chưa triển khai vì:

- Tích hợp OmniVoice upstream vẫn chưa phải runtime production rõ ràng.
- Cần theo dõi issue upstream.
- Đây vẫn là hướng tiềm năng nhất nếu muốn vượt giới hạn Python/PyTorch.

## Trạng thái vận hành hiện tại

Lệnh chuẩn cho chương dài:

```bash
ov /mnt/hdd2tb/Book/Wheel_Of_Time/B6/Translated/B6-CH11/B6-CH11.md --resume
```

Nếu muốn override thủ công:

```bash
ov-linux chapter.md --parallel-chunks 4 --torch-threads 32 --num-step 16 --resume
```

Nếu muốn dùng OpenVINO để giảm RAM/model footprint:

```bash
ov-openvino chapter.md --resume
```

Nếu muốn chạy batch nhiều file:

```bash
batch-numa --resume /path/to/folder
```

## Đánh giá cuối

Mục tiêu “chạy được TTS local trên Linux” đã hoàn thành. Hệ thống hiện có:

- Local OmniVoice không cần API.
- Voice cloning từ sample trong `voices/default/`.
- Python 3.12 isolated env.
- CPU-only PyTorch.
- NUMA pinning.
- Parallel chunks.
- Resume/checkpoint từng chunk.
- OpenVINO FP32/W8A8 experimental backend.
- Global command đơn giản `ov file.md --resume`.

Mục tiêu “RTF < 1.0 trên Xeon E5-2670” không đạt. Đây không còn là vấn đề cấu hình phần mềm đơn thuần, mà là giới hạn phần cứng: CPU thiếu các lệnh vector/matrix hiện đại cần cho inference INT8/BF16 tốc độ cao.

Hướng tối ưu tiếp theo nếu muốn nhanh hơn đáng kể:

1. Theo dõi và thử `sherpa-onnx` khi OmniVoice C++ backend ổn định.
2. Thử community `omnivoice.cpp`/GGUF nếu parity đủ tốt.
3. Nếu mục tiêu là audiobook tiếng Việt nhanh hơn OmniVoice, thử Piper/Sherpa-ONNX Vietnamese.
4. Nếu vẫn dùng OmniVoice trên máy này, cấu hình hiện tại là lựa chọn thực dụng nhất.

# Text-To-Speech-Gemini

A production-ready audiobook generator using Google's Gemini 2.5 TTS API with advanced features including multi-API key rotation, concurrent processing, intelligent 3-level text chunking, error recovery, and checkpoint-based resume.

## 🎯 Project Overview

Convert Markdown chapters into high-quality audiobook files (`.wav`) using Google's Gemini Text-to-Speech API with native multi-speaker support and controllable speech.

**Key Highlights:**
- ⚡ **Concurrent processing** with ThreadPoolExecutor for 2-3× speed improvement
- 🔄 **Queue-based key rotation** with intelligent cooldown mechanism (0 wasted retries!) ⭐ NEW!
- 💾 **Resume feature** automatically resumes from checkpoint (91% quota savings!)
- 🎙️ **30 prebuilt voices** with natural language control
- 🔒 **Thread-safe** quota tracking and key assignment
- 📊 **Real-time progress tracking** with detailed metrics

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/TTTV273/Text-To-Speech-Gemini.git
cd Text-To-Speech-Gemini

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt
```

### Setup API Keys

Create a `.env` file with your Gemini API keys:

```bash
# .env
GEMINI_API_KEY_1=your_first_key_here
GEMINI_API_KEY_2=your_second_key_here
GEMINI_API_KEY_3=your_third_key_here
# ... GEMINI_API_KEY_N (where N is the key number, e.g., GEMINI_API_KEY_8, GEMINI_API_KEY_9, etc.)
```

**Get API keys:** https://aistudio.google.com/app/apikey

---

## 📖 Usage

### Basic Usage (Synchronous Mode)

```bash
# Process a single chapter
uv run audiobook_generator.py path/to/chapter.md

# With custom voice
uv run audiobook_generator.py path/to/chapter.md --voice Puck
```

### ⚡ Concurrent Mode (Recommended for Speed)

```bash
# Use 3 workers (default)
uv run audiobook_generator.py chapter.md --concurrent

# Use 5 workers (faster for large files)
uv run audiobook_generator.py chapter.md --concurrent --workers 5

# Maximum speed (7 workers)
uv run audiobook_generator.py chapter.md --concurrent --workers 7
```

### Local OmniVoice Mode

Use this when you want local TTS with OmniVoice (600+ languages, voice cloning, voice design) instead of the Gemini API. No API key required.

`./ov` is the Mac/MPS-oriented launcher. For Linux CPU machines, use `./ov-linux` instead.

**Quick start:**

```bash
# Default voice (Kore)
./ov chapter.md

# Named voice
./ov Kore chapter.md

# With advanced options
./ov chapter.md --num-step 50 --speed 1.0
```

Output is an `.mp3` file created next to the input file.

**Voice samples layout:**

```text
voices/
├── default/
│   ├── Kore.mp3    # 3-10s reference audio
│   └── Kore.txt    # Exact transcript of the audio
└── <voice_name>/   # Custom voice
    ├── <voice_name>.mp3
    └── <voice_name>.txt
```

`voices/` is gitignored — voice samples are personal data, do not commit them.

**Advanced options:**

```bash
./ov chapter.md --device mps          # Apple Silicon GPU (default)
./ov chapter.md --device cpu          # Force CPU
./ov chapter.md --num-step 50         # Diffusion steps (default: 50)
./ov chapter.md --speed 1.0           # Speech speed (default: 1.0)
./ov chapter.md --language vi         # Language (default: vi)
./ov chapter.md --max-tokens 500      # Max tokens per chunk
./ov chapter.md --no-normalize        # Disable Vietnamese text normalization
./ov chapter.md --overwrite           # Overwrite existing output
./ov chapter.md --keep-wav            # Keep intermediate WAV
./ov chapter.md --resume             # Resume from checkpoint after error
./ov chapter.md --output custom.mp3   # Custom output path
```

### Local OmniVoice on Linux CPU

Use this path for Linux machines where CUDA is not viable, especially old dual-socket Xeon systems. Keep `omnivoice_generator.py` and `./ov` for Mac; Linux uses `omnivoice_linux_generator.py` and `./ov-linux`.

**Recommended environment:**

```bash
# Use Python 3.12 or 3.11. Avoid system Python 3.14 for OmniVoice/PyTorch.
python3.12 -m venv .venv-omnivoice
source .venv-omnivoice/bin/activate

# Install CPU-only PyTorch first. Do not install CUDA wheels for old Kepler GPUs.
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-omnivoice-linux.txt
```

Arch Linux system packages:

```bash
sudo pacman -S ffmpeg numactl
```

**Baseline run:**

```bash
./ov-linux chapter.md
./ov-linux Kore chapter.md --resume
```

Linux defaults are CPU-safe:

```text
device: cpu
dtype: float32
num-step: 16
torch threads: 16
torch inter-op threads: 1
```

**Benchmark thread counts:**

```bash
./ov-linux chapter.md --torch-threads 8 --overwrite
./ov-linux chapter.md --torch-threads 16 --overwrite
./ov-linux chapter.md --torch-threads 32 --overwrite
```

For Xeon E5-2670 dual-socket systems, `16` is the single-process baseline. `32` is only a benchmark check because SMT can slow down matrix-heavy inference.

**Batch parallel across 2 NUMA nodes:**

```bash
# All .md files in a directory, split across both sockets
scripts/batch_numa.sh 2.DATA/BOOK-2_Learn-Python

# With resume + OpenVINO backend
scripts/batch_numa.sh --resume --openvino 2.DATA/BOOK-2_Learn-Python
```

This distributes files evenly: even-indexed files run on node 0, odd-indexed on node 1, each pinned with `numactl --cpunodebind --membind`. 8 threads per process = 16 physical cores total.

**NUMA-pinned single file:**

```bash
./scripts/ov_linux_numa.sh 0 chapter.md
./scripts/ov_linux_numa.sh 1 Kore chapter.md --resume
```

The NUMA launcher defaults to 8 threads per process and pins CPU execution plus memory allocation to one socket. For batch audiobook work, run one process on node 0 and another on node 1 for different files/chunks.

**Parallel chunks within a single file:**

```bash
# Split chunks across 2 NUMA nodes, 2 workers run in parallel
ov-linux chapter.md --parallel-chunks 2 --resume
```

Each worker loads the model once, generates its assigned chunks (interleaved: node 0 gets chunks 1,3,5..., node 1 gets 2,4,6...), and writes WAV files. The parent process merges all chunks in order and converts to MP3. Falls back to sequential if fewer than 2 chunks.

### OpenVINO Phase (experimental)

`ov-openvino` uses an OpenVINO IR model instead of native PyTorch for the LLM forward pass. Convert the model first, then run:

```bash
# One-time conversion (FP32 IR, ~1.2 GB)
.venv-omnivoice/bin/python scripts/convert_omnivoice_openvino.py

# Optional: W8A8 quantization (~587 MB)
.venv-omnivoice/bin/python scripts/quantize_omnivoice_openvino.py

# Run (auto-selects W8A8 if available, falls back to FP32)
./ov-openvino chapter.md
./ov-openvino-numa 0 chapter.md
```

Install OpenVINO deps:

```bash
pip install -r requirements-openvino.txt
```

**Benchmark on Xeon E5-2670 (50 steps, 39 tokens, 16 threads):**

| Backend           | Wall time | Model size | RTF   |
|-------------------|-----------|------------|-------|
| PyTorch FP32      | 232s      | 1.6 GB     | ~51   |
| OpenVINO FP32     | 237s      | 1.2 GB     | ~52   |
| OpenVINO W8A8     | 236s      | 587 MB     | ~52   |

On Sandy Bridge Xeon (AVX-only, no VNNI/AMX), OpenVINO does not outperform native PyTorch. INT8 speedup requires AVX-512 VNNI or AMX (available on Ice Lake+). The W8A8 model is still useful for its smaller memory footprint.

### Performance Comparison

| File Size | Sequential | Concurrent (3 workers) | Speedup |
|-----------|------------|------------------------|---------|
| 8 chunks  | 160s       | 60s                    | 2.6×    |
| 9 chunks  | 180s       | 60s                    | 3.0×    |
| 12 chunks | 240s       | 50s (5 workers)        | 4.8×    |

**Real-world example:** Processing an entire book (30 chapters)
- Sequential: 80 minutes
- Concurrent: 30 minutes
- **Saves 50 minutes per book!** ⚡

### 🔄 Resume Mode (NEW - Phase 8)

Resume from checkpoint when processing fails mid-chapter:

```bash
# Resume from last checkpoint (skip completed chunks)
uv run audiobook_generator.py chapter.md --concurrent --resume

# Works with any worker count
uv run audiobook_generator.py chapter.md --concurrent --workers 5 --resume
```

**How it works:**
1. Processing fails mid-chapter (e.g., 10/11 chunks complete)
2. System saves checkpoint (`.checkpoint_*.json`) and partial audio
3. Run again with `--resume` flag
4. Only processes missing chunks (91% API quota savings!)
5. Merges existing + new audio automatically
6. Cleans up checkpoint on success

**Example scenario:**
```
Day 1: Process B2-CH05 (11 chunks)
  → 10/11 complete, chunk 11 fails (quota exhausted)
  → Saved: B2-CH05_PARTIAL.wav (99MB) + checkpoint

Day 2: Resume with --resume flag
  → Loads existing 10 chunks from partial file
  → Only processes chunk 11 (1 API request)
  → Saves 10 API requests (91% quota savings!)
  → Final: B2-CH05.wav (complete)
```

**Benefits:**
- **Quota savings:** 91% reduction for B2-CH05 example (11 → 1 request)
- **Time savings:** 89% faster (180s → 20s)
- **Automatic validation:** SHA256 file hash prevents processing modified files
- **Safe fallback:** Invalid checkpoint → full processing

---

## 🎙️ Voice Options

Choose from 30 prebuilt voices:

**Popular voices:**
- `Kore` - Default, neutral (recommended)
- `Puck` - Upbeat, energetic
- `Charon` - Deep, authoritative
- `Aoede` - Warm, storytelling
- `Enceladus` - Breathy, tired

**Full list:** See [Gemini TTS Voice Documentation](https://ai.google.dev/gemini-api/docs/models/gemini#gemini-2.0-flash-exp)

---

## ✨ Features

### Phase 5: Multi-API Key Rotation ✅
- Supports any number of API keys (GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...) with automatic rotation
- **Bug Fix:** Correctly assigns and utilizes individual keys for concurrent workers, significantly reducing `Rate Limit` and `Model Overloaded` errors.
- Intelligent quota management (10 requests/day per key)
- Daily usage tracking in `api_usage.json`
- Automatic fallback when keys are exhausted

### Phase 6: Error Recovery ✅
- **Soft-fail detection:** Handles both explicit errors (429) and implicit failures (empty content)
- **Enhanced Retry Logic:** Now includes robust retries for `503 UNAVAILABLE` (`Model Overloaded`) server errors, improving resilience during high API load.
- **Partial save:** Preserves completed chunks if processing fails mid-chapter
- **Automatic retry:** 3 retries per key with exponential backoff
- **Graceful degradation:** Save what you can, report what failed

### Phase 7: Concurrent Processing ✅
- **ThreadPoolExecutor:** Process multiple chunks simultaneously
- **Intelligent Load Balancing:** Dynamic distribution strategy that spreads chunks evenly across ALL available keys, preventing "hotspot" bottlenecks.
- **Round-robin key assignment:** Distribute load evenly across all keys
- **Thread-safe quota management:** Lock-based synchronization
- **Order preservation:** Chunks assembled in correct sequence
- **Configurable workers:** 1-7 workers (recommend 3-5 for optimal performance)

### Phase 8: Resume Feature ✅
- **Checkpoint system:** Automatically saves progress when processing fails
- **Smart resume:** Only processes missing chunks (91% quota savings!)
- **File validation:** SHA256 hash prevents processing modified files
- **Auto-merge:** Combines existing + new audio seamlessly
- **Auto-cleanup:** Removes checkpoint files on successful completion
- **CLI flag:** Simple `--resume` flag to enable resume mode

### Phase 9: Text Chunker Refactor ✅
- **3-level intelligent splitting:** Paragraph → Sentence → Word hierarchy
- **Bug fix:** Fixed critical indentation bug causing 0 chunks for large files
- **Modular design:** Separate `text_chunker.py` module for reusability
- **Comprehensive testing:** 6 unit tests covering all edge cases
- **Smart sentence detection:** Regex-based sentence boundary detection
- **Logging support:** DEBUG/INFO/WARNING levels for troubleshooting
- **Handles edge cases:** Large paragraphs (>2000 tokens), no paragraph breaks, Vietnamese text

### Phase 10: Queue-based Key Rotation ✅ NEW!
- **Zero-waste retry strategy:** Immediately rotates to next key on failure (no retries with same key)
- **Intelligent cooldown:** Failed keys enter 30s cooldown queue, auto-return when ready
- **Error classification:** Distinguishes QUOTA_EXHAUSTED (remove) vs MODEL_OVERLOAD (cooldown)
- **Thread-safe queue management:** Lock-based synchronization for concurrent access
- **Auto-recovery:** Keys automatically return to available pool after cooldown
- **Smart waiting:** When all keys cooldown, waits for shortest cooldown time
- **Permanent removal:** Quota-exhausted keys removed from rotation permanently
- **Performance boost:** ~9 minutes saved per error (0 wasted retry time vs 90s×6 keys)

### Core Features:
- **Intelligent chunking:** 3-level splitting (paragraph/sentence/word) with configurable chunk size (default: 1000 tokens)
- **Markdown cleaning:** Removes headers, bold, italic, links, code blocks
- **Token counting:** Uses tiktoken for accurate token estimation
- **WAV output:** 16-bit PCM, 24kHz, mono format
- **Progress tracking:** Real-time updates for concurrent processing
- **CLI interface:** User-friendly command-line arguments
- **Modular architecture:** Separate modules for chunking, API management, TTS generation

---

## 📂 Output

Audio files are saved in a `TTS` subdirectory next to the source file:

```
your-book/
├── B2-CH01.md
├── B2-CH02.md
└── TTS/
    ├── B2-CH01.wav                 # Complete file
    ├── B2-CH01_PARTIAL.wav         # Partial save (if error occurred)
    ├── .checkpoint_B2-CH01.json    # Resume checkpoint (auto-deleted on success)
    └── B2-CH02.wav
```

**File types:**
- `.wav` - Final complete audio file
- `_PARTIAL.wav` - Partial progress (when processing fails mid-chapter)
- `.checkpoint_*.json` - Resume checkpoint (hidden, auto-cleaned up)

---

## 🔧 Configuration

### Chunk Size Configuration

**Location:** `audiobook_generator.py:27`

```python
MAX_TOKENS_PER_CHUNK = 1000  # Adjust this value to change chunk size
```

**Recommended values:**
- **1000 tokens** (default) - Best audio quality, minimal distortion
- **1500 tokens** - Balanced quality and speed
- **2000 tokens** - Faster processing, may have slight distortion

**When to adjust:**
- Audio has distortion/noise → Decrease to 500-750 tokens
- Need faster processing → Increase to 1500-2000 tokens
- Testing audio quality → Try different values

**Impact:**
- Lower value = More chunks = Better quality + More API requests
- Higher value = Fewer chunks = Faster processing + Potential distortion

### Worker Count Recommendations

- **Small files (2-5 chunks):** `--workers 3` (default)
- **Medium files (6-10 chunks):** `--workers 5`
- **Large files (10+ chunks):** `--workers 7`

### API Rate Limits

**Free tier:** 10 requests per day per key (updated 2025-12-13)

**With 13 keys:**
- Total: 130 requests/day
- ~130 chapters/day (1 chunk each)
- ~14-16 large chapters/day (8-9 chunks each)

---

## 📊 API Usage Tracking

The system automatically tracks API usage in `api_usage.json`:

```json
{
  "date": "2025-11-03",
  "keys": {
    "464d634f": {
      "requests": 4,
      "last_error": null,
      "last_used": "2025-11-03T01:49:23"
    }
  },
  "current_key_index": 5
}
```

**Auto-reset:** Counters reset at midnight (daily quota)

---

## 🐛 Error Handling

### Partial Save

If processing fails mid-chapter, completed chunks are automatically saved:

```
💾 Saved partial progress (6/12 chunks):
   File: B2-CH01_PARTIAL.wav
   Size: 60.75 MB
   ℹ️  You can listen to completed chunks while investigating the error.
```

### Retry Logic

- **Per-key retries:** 3 attempts with 30s delay
- **Key rotation:** Automatic switch to next available key
- **Exhaustion handling:** Clear error message when all keys depleted

---

## 🎓 Technical Details

### Architecture

- **Language:** Python 3.12+
- **TTS Model:** Gemini 2.5 Flash Preview TTS
- **Token Counter:** tiktoken (cl100k_base encoding)
- **Concurrency:** ThreadPoolExecutor (thread-based parallelism)
- **Audio Format:** WAV (PCM 16-bit, 24kHz, mono)

### Thread Safety

- All shared state protected with `threading.Lock()`
- Lock-based synchronization for:
  - API key usage tracking
  - Quota management
  - Results storage
  - Progress counters

### Key Assignment Strategy

**Smart Dynamic Distribution:**
1. **Filter:** Identify all currently available (non-exhausted) keys.
2. **Distribute:** Assign chunks using `chunk_id % available_keys_count`.
3. **Benefit:** Prevents the "thundering herd" problem where all workers flock to the single next available key, ensuring even load distribution across all remaining quota.

**Fallback:** If assigned key is exhausted during processing, automatically rotate to next available key.

---

## 📝 Development

### Project Structure

```
Text-To-Speech-Gemini/
├── audiobook_generator.py       # Main processing script
├── api_key_manager.py           # Multi-key quota tracking & usage logging
├── key_rotation_manager.py      # Queue-based key rotation with cooldown ⭐ NEW!
├── text_chunker.py              # 3-level intelligent text chunking
├── api_usage.json               # Daily usage tracking (auto-generated)
├── .env                         # API keys (not committed)
├── requirements.txt             # Python dependencies
├── PLAN.md                      # Detailed implementation plan (all phases)
├── CLAUDE.md                    # AI collaboration guidelines
└── README.md                    # This file
```

### Key Files

- **audiobook_generator.py:** Core TTS processing with sync + concurrent modes
- **api_key_manager.py:** Thread-safe quota tracking and daily usage logging
- **key_rotation_manager.py:** Queue-based key rotation with intelligent cooldown mechanism ⭐ NEW!
- **text_chunker.py:** 3-level intelligent text splitting (paragraph/sentence/word)
- **PLAN.md:** Complete project history with all 10 implementation phases

### Testing

```bash
# Test basic functionality
uv run audiobook_generator.py test_concurrent_mini.md

# Test concurrent mode
uv run audiobook_generator.py test_concurrent_mini.md --concurrent --workers 3

# Benchmark performance
time uv run audiobook_generator.py chapter.md --concurrent --workers 3
time uv run audiobook_generator.py chapter.md  # Compare with sync
```

---

## 🔮 Future Enhancements

**Planned features:**
- [ ] Progress bar with `tqdm`
- [ ] `--benchmark` flag for automatic performance comparison
- [ ] `--dry-run` to estimate time without processing
- [ ] `--resume` flag to continue from checkpoint
- [ ] Multi-speaker support with dialogue detection
- [ ] Custom voice training

---

## 📚 Documentation

**Full implementation details:** See [PLAN.md](PLAN.md)

**Key phases:**
- Phase 1-4: Basic TTS + chunking support
- Phase 5: Multi-API key rotation
- Phase 6: Error recovery + partial save
- Phase 7: Concurrent processing
- Phase 8: Resume feature
- Phase 9: Text chunker refactor
- Phase 10: Queue-based key rotation (current) ⭐ NEW!

**API Documentation:** [Gemini TTS API](https://ai.google.dev/gemini-api/docs/models/gemini)

---

## 🤝 Contributing

This is a personal learning project, but suggestions are welcome! Please open an issue for discussion.

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🙏 Acknowledgments

- Google Gemini API for high-quality TTS
- Claude Code for implementation assistance
- Robert Jordan's "The Wheel of Time" series (test use case)

---

## 📧 Contact

Created by [@TTTV273](https://github.com/TTTV273)

**Issues?** Please report at: https://github.com/TTTV273/Text-To-Speech-Gemini/issues

---

**Last Updated:** 2025-12-13 (Queue-based Key Rotation with Intelligent Cooldown - Phase 10)

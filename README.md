# Text-To-Speech-Gemini

A production-ready audiobook generator using Google's Gemini 2.5 TTS API with advanced features including multi-API key rotation, concurrent processing, intelligent 3-level text chunking, error recovery, and checkpoint-based resume.

## 🎯 Project Overview

Convert Markdown chapters into high-quality audiobook files (`.wav`) using Google's Gemini Text-to-Speech API with native multi-speaker support and controllable speech.

**Key Highlights:**
- ⚡ **Concurrent processing** with ThreadPoolExecutor for 2-3× speed improvement
- 🔄 **Multi-API key rotation** supporting up to 7 keys with automatic quota management
- 💾 **Resume feature** automatically resumes from checkpoint (91% quota savings!) ⭐ NEW!
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
- Intelligent quota management (15 requests/day per key)
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

### Phase 9: Text Chunker Refactor ✅ NEW!
- **3-level intelligent splitting:** Paragraph → Sentence → Word hierarchy
- **Bug fix:** Fixed critical indentation bug causing 0 chunks for large files
- **Modular design:** Separate `text_chunker.py` module for reusability
- **Comprehensive testing:** 6 unit tests covering all edge cases
- **Smart sentence detection:** Regex-based sentence boundary detection
- **Logging support:** DEBUG/INFO/WARNING levels for troubleshooting
- **Handles edge cases:** Large paragraphs (>2000 tokens), no paragraph breaks, Vietnamese text

### Core Features:
- **Intelligent chunking:** 3-level splitting (paragraph/sentence/word) with edge case handling
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

### Worker Count Recommendations

- **Small files (2-5 chunks):** `--workers 3` (default)
- **Medium files (6-10 chunks):** `--workers 5`
- **Large files (10+ chunks):** `--workers 7`

### API Rate Limits

**Free tier:** 15 requests per day per key

**With 7 keys:**
- Total: 105 requests/day
- ~105 chapters/day (1 chunk each)
- ~11-12 large chapters/day (9 chunks each)

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

**Round-robin distribution:**
```
Chunk 0 → Key 0
Chunk 1 → Key 1
Chunk 2 → Key 2
...
Chunk 7 → Key 0 (wrap around)
```

**Fallback:** If assigned key is exhausted, find next available key

---

## 📝 Development

### Project Structure

```
Text-To-Speech-Gemini/
├── audiobook_generator.py    # Main processing script
├── api_key_manager.py         # Multi-key rotation + quota tracking
├── api_usage.json             # Daily usage tracking (auto-generated)
├── .env                       # API keys (not committed)
├── requirements.txt           # Python dependencies
├── PLAN.md                    # Detailed implementation plan (all phases)
├── CLAUDE.md                  # AI collaboration guidelines
└── README.md                  # This file
```

### Key Files

- **audiobook_generator.py:** Core TTS processing with sync + concurrent modes
- **api_key_manager.py:** Thread-safe quota management and key rotation
- **PLAN.md:** Complete project history with all 7 implementation phases

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
- Phase 9: Text chunker refactor (current) ⭐ NEW!

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

**Last Updated:** 2025-12-02 (API Key Management and Error Handling Improvements)
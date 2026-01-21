# AGENTS.md

Guidelines for AI coding agents working in the Text-To-Speech-Gemini repository.

## Project Overview

Python-based audiobook generator using Google Gemini 2.5 TTS API. Converts markdown/text files to speech with multi-key rotation, concurrent processing, and checkpoint/resume support.

**Tech Stack:** Python 3.12+, google-genai, tiktoken, python-dotenv

## Quick Reference

| Aspect | Details |
|--------|---------|
| Language | Python 3.12+ |
| API | Google Gemini TTS (gemini-2.5-flash-preview-tts) |
| Audio Format | WAV (PCM 16-bit, 24kHz, mono) |
| Token Limit | 1000 tokens per chunk (configurable) |
| Concurrency | ThreadPoolExecutor (1-7 workers) |

---

## Build & Run Commands

### Environment Setup
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Single file processing
python audiobook_generator.py input.md --voice Kore --workers 3

# Batch processing
./run_batch.sh

# Process folder
./TTS_Folder.sh /path/to/folder

# Convert WAV to MP3
./convert_wav_to_mp3.sh
```

### Testing
```bash
# Run inline tests in text_chunker.py
python -c "from text_chunker import run_tests; run_tests()"

# Manual validation
python -c "from validators import ValidationResult; print('OK')"
```

**Note:** No formal test framework (pytest) is configured. Tests are inline functions.

### Linting
No linting tools configured. When adding new code, follow existing patterns.

---

## Code Style Guidelines

### Import Organization
Group imports in this order with blank lines between groups:
```python
# 1. Standard library imports (alphabetical)
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# 2. Third-party imports
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# 3. Local imports
from api_key_manager import APIKeyManager
from text_chunker import count_tokens, split_into_chunks
```

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Functions | snake_case | `generate_audio_data()`, `clean_markdown()` |
| Classes | PascalCase | `APIKeyManager`, `KeyRotationManager` |
| Constants | UPPER_SNAKE_CASE | `MAX_TOKENS_PER_CHUNK = 1000` |
| Variables | snake_case | `current_chunk`, `total_tokens` |
| Files | snake_case | `api_key_manager.py`, `text_chunker.py` |

### Type Hints
Use type hints for function signatures. Import from `typing` when needed:
```python
from typing import List, Optional, Tuple

def split_by_words(text: str, max_tokens: int) -> List[str]:
    ...

def verify_checkpoint(checkpoint, file_path, output_dir) -> Tuple[bool, list, str]:
    ...
```

### Docstrings
Use Google-style docstrings with Args, Returns, and Raises sections:
```python
def generate_audio_data(client, text, voice="Kore", rotation_manager=None):
    """
    Generate audio with automatic key rotation.

    Args:
        client: Gemini client (unused, kept for backwards compatibility)
        text: Text to convert to speech
        voice: Voice name (default: Kore)
        rotation_manager: KeyRotationManager instance (required)

    Returns:
        bytes: Audio data

    Raises:
        Exception: If all keys fail or are exhausted
    """
```

### Error Handling
- Use specific exception types (e.g., `ClientError` from google.genai)
- Classify errors for retry logic (QUOTA_EXHAUSTED, RATE_LIMIT, MODEL_OVERLOAD)
- Log warnings with context: `logger.warning(f"Token counting failed: {e}")`

```python
try:
    response = client.models.generate_content(...)
except ClientError as e:
    error_type = classify_error(e)
    if error_type == "QUOTA_EXHAUSTED":
        rotation_manager.remove_key(current_key)
    elif error_type == "RATE_LIMIT":
        rotation_manager.cooldown_key(current_key, 30)
```

### Thread Safety
Use `threading.Lock()` for shared resources in concurrent code:
```python
class APIKeyManager:
    def __init__(self):
        self.lock = threading.Lock()

    def increment_usage(self, key):
        with self.lock:
            # Thread-safe operation
            self.usage_data["keys"][key_hash]["requests"] += 1
```

### Path Handling
Use `pathlib.Path` consistently instead of `os.path`:
```python
from pathlib import Path

output_dir = Path("TTS") / "output"
checkpoint_file = output_dir / f".checkpoint_{file_path.stem}.json"
```

---

## API Integration Patterns

### Gemini TTS Configuration
```python
from google import genai
from google.genai import types

response = client.models.generate_content(
    model="gemini-2.5-flash-preview-tts",
    contents=text,
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
```

### Audio Data Extraction
```python
audio_data = response.candidates[0].content.parts[0].inline_data.data
```

### WAV File Writing
```python
import wave

with wave.open(str(output_path), "wb") as wav_file:
    wav_file.setnchannels(1)        # Mono
    wav_file.setsampwidth(2)        # 16-bit
    wav_file.setframerate(24000)    # 24kHz
    wav_file.writeframes(audio_data)
```

---

## Project Structure

```
Text-To-Speech-Gemini/
├── audiobook_generator.py    # Main TTS processing (entry point)
├── api_key_manager.py        # Multi-key quota tracking
├── key_rotation_manager.py   # Queue-based key rotation
├── text_chunker.py           # 3-level text chunking logic
├── validators.py             # Input validation utilities
├── requirements.txt          # Python dependencies
├── .env                      # API keys (GEMINI_API_KEY_1, etc.)
├── CLAUDE.md                 # Claude Code instructions
├── GEMINI.md                 # Gemini CLI instructions
└── TTS/                      # Output directory
```

---

## Environment Variables

Required in `.env` file:
```bash
GEMINI_API_KEY_1=your_first_api_key
GEMINI_API_KEY_2=your_second_api_key
# ... add more keys for rotation
```

---

## Common Tasks

### Adding a New Voice
Voices available: Kore, Puck, Zephyr, Enceladus, and 26 others.
See `3.RESOURCES/251028-Speech_generation.md` for full list.

### Modifying Chunk Size
Edit `MAX_TOKENS_PER_CHUNK` in `audiobook_generator.py`:
```python
MAX_TOKENS_PER_CHUNK = 1000  # Change this value
```

### Adding Error Classification
Update `classify_error()` function in `audiobook_generator.py`:
```python
def classify_error(error: Exception) -> str:
    # Add new error patterns here
    if 'new_error_pattern' in str(error):
        return "NEW_ERROR_TYPE"
```

---

## Language Note

This codebase contains mixed English/Vietnamese comments and output messages. Maintain consistency with surrounding code when making changes.

# Text-To-Speech-Gemini

This project is a Python-based audiobook generator that utilizes the Google Gemini API (specifically `gemini-2.5-flash-preview-tts`) to convert Markdown text files into spoken audio (WAV format). It supports both sequential and concurrent processing, with features for text cleaning, chunking, and resuming interrupted generations.

## Project Structure

The core logic resides in the parent directory, with `TTS/` serving primarily as an output or working directory for the current session.

### Key Files (in Parent Directory)

*   **`audiobook_generator.py`**: The main application script.
    *   **Functionality**: Handles file reading, markdown cleaning, token counting, chunking, API interaction, and audio saving.
    *   **Key Features**:
        *   `process_chapter_concurrent`: Orchestrates multi-threaded processing.
        *   `save_checkpoint` / `load_checkpoint`: Manages state for the resume feature.
        *   `clean_markdown`: Prepares text for TTS by removing formatting.
*   **`text_chunker.py`**: (Inferred) Module for `count_tokens` and `split_into_chunks`.
*   **`api_key_manager.py`**: (Inferred) Manages API key rotation and usage tracking.

## Usage

The application is run via the command line from the project root.

### Basic Command

```bash
python audiobook_generator.py <path_to_markdown_file>
```

### Advanced Options

*   **`--voice <name>`**: Specify the voice (default: "Kore").
*   **`--concurrent`**: Enable multi-threaded processing for faster generation.
*   **`--workers <n>`**: Set the number of concurrent workers (default: 3, max: 7).
*   **`--resume`**: Attempt to resume from a previous partial generation.

### Example

```bash
python audiobook_generator.py 2.DATA/BOOK-2_Learn-Python/B2-CH02.md --concurrent --workers 5 --resume
```

## Development Notes

### Audio Generation Flow
1.  **Input**: Markdown file.
2.  **Preprocessing**: Text is cleaned and split into chunks (< 2000 tokens).
3.  **Processing**:
    *   **Sequential**: Chunks are processed one by one.
    *   **Concurrent**: Chunks are distributed to a thread pool.
4.  **Assembly**: Audio parts are concatenated.
    *   *Note*: The current merge logic simply appends new chunks to existing partial audio.
5.  **Output**: Final WAV file saved in `TTS/` directory.

### Resume Logic Limitation
The current resume implementation appends newly generated chunks to the end of the `_PARTIAL.wav` file. It **does not** support inserting chunks into the middle of an existing partial file. If chunks are generated out of order (e.g., 1 and 5 exist, then 2, 3, 4 are generated), the final audio will be out of sequence (1, 5, 2, 3, 4).

### Environment
*   Requires `GEMINI_API_KEY` (managed via `.env` or `api_key_manager`).
*   Output audio format: WAV (24kHz, Mono).

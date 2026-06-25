import argparse
import hashlib
import json
import re
import subprocess
import sys
import wave
from datetime import datetime
from pathlib import Path

DEFAULT_VOICE = "Kore"
DEFAULT_VOICE_DIR = Path(__file__).parent / "voices"
MAX_TOKENS_PER_CHUNK = 500
SAMPLE_RATE = 24000
AUDIO_EXTENSIONS = [".wav", ".mp3", ".MP3", ".m4a", ".flac"]
WORDS_PER_TOKEN = 0.77
TOKENS_PER_CHAR = 0.25


# ============================================================
# Markdown Cleaning
# ============================================================


def clean_markdown(text: str) -> str:
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


# ============================================================
# Fallback Chunker (when tiktoken unavailable)
# ============================================================


def count_tokens_fallback(text: str) -> int:
    words = len(text.split())
    chars = len(text)
    return max(int(words / WORDS_PER_TOKEN), int(chars * TOKENS_PER_CHAR))


def split_into_chunks_fallback(text: str, max_tokens: int) -> list[str]:
    max_words = max(1, int(max_tokens * WORDS_PER_TOKEN))
    paragraphs = text.split("\n\n")

    chunks = []
    current = []
    current_words = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_words = len(para.split())

        if current_words + para_words <= max_words:
            current.append(para)
            current_words += para_words
        elif para_words <= max_words:
            if current:
                chunks.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_words = 0
            sentences = re.split(r"(?<=[.!?…。！？])\s+", para)
            for sent in sentences:
                sent_words = len(sent.split())
                if current_words + sent_words <= max_words:
                    current.append(sent)
                    current_words += sent_words
                else:
                    if current:
                        chunks.append(" ".join(current))
                    current = [sent] if sent_words <= max_words else []
                    current_words = sent_words if sent_words <= max_words else 0
                    if sent_words > max_words:
                        words = sent.split()
                        for i in range(0, len(words), max_words):
                            chunks.append(" ".join(words[i:i + max_words]))

    if current:
        chunks.append("\n\n".join(current) if len(current) > 1 and "\n" in current[0] else " ".join(current))

    return chunks if chunks else [text]


def load_text_chunker():
    try:
        from text_chunker import count_tokens, split_into_chunks
        return count_tokens, split_into_chunks
    except ImportError as exc:
        if exc.name != "tiktoken" and "tiktoken is required" not in str(exc):
            raise
        print("ℹ️  tiktoken not available, using word-based chunking fallback")
        return count_tokens_fallback, split_into_chunks_fallback


# ============================================================
# Voice Resolution
# ============================================================


def resolve_voice(voice_name: str, voice_dir: Path) -> tuple[Path, str]:
    """
    Resolve a voice to (audio_path, ref_text).

    Convention:
      voices/default/  → Kore.<ext> + Kore.txt
      voices/<name>/   → <name>.<ext> + <name>.txt

    Supports: .wav .mp3 .MP3 .m4a .flac (case-insensitive)

    Returns:
        (audio_path, ref_text)

    Raises:
        FileNotFoundError with clear message if files missing.
        ValueError if voice_name contains path separators or unsafe chars.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", voice_name):
        raise ValueError(
            f"Invalid voice name: '{voice_name}'\n"
            "Voice names may only contain letters, numbers, hyphens, and underscores."
        )

    if voice_name == "default":
        folder = voice_dir / "default"
        name = DEFAULT_VOICE
    else:
        folder = voice_dir / voice_name
        name = voice_name

    if not folder.exists():
        raise FileNotFoundError(
            f"Voice folder not found: {folder}\n"
            f"Expected structure: voices/{voice_name}/{name}.<wav|mp3> + {name}.txt"
        )

    # Find audio file (case-insensitive extension)
    audio_path = None
    for ext in AUDIO_EXTENSIONS:
        candidate = folder / f"{name}{ext}"
        if candidate.exists():
            audio_path = candidate
            break

    # Fallback: any file matching name.* that is audio
    if audio_path is None:
        for candidate in folder.iterdir():
            if candidate.stem == name and candidate.suffix in AUDIO_EXTENSIONS:
                audio_path = candidate
                break

    if audio_path is None:
        raise FileNotFoundError(
            f"Audio file not found in {folder}/\n"
            f"Expected: {name}.wav (or .mp3, .m4a, .flac)"
        )

    # Find reference text
    ref_text_path = folder / f"{name}.txt"
    if not ref_text_path.exists():
        # Case-insensitive fallback
        for candidate in folder.iterdir():
            if candidate.stem == name and candidate.suffix.lower() == ".txt":
                ref_text_path = candidate
                break

    if not ref_text_path.exists():
        raise FileNotFoundError(
            f"Reference text not found in {folder}/\n"
            f"Expected: {name}.txt"
        )

    ref_text = ref_text_path.read_text(encoding="utf-8").strip()

    print(f"🎙️  Voice: {voice_name}")
    print(f"   Audio: {audio_path.name}")
    print(f"   Ref text: {ref_text[:60]}{'...' if len(ref_text) > 60 else ''}")

    return audio_path, ref_text


# ============================================================
# Path Helpers
# ============================================================


def get_default_output_path(input_file: str, voice_name: str) -> Path:
    input_path = Path(input_file)
    if voice_name == "default":
        return input_path.parent / f"{input_path.stem}.mp3"
    return input_path.parent / f"{input_path.stem}_{voice_name}.mp3"


def get_chunk_path(output_path: Path, chunk_index: int) -> Path:
    return output_path.parent / f".chunk_{chunk_index}_{output_path.stem}.wav"


def get_temp_wav_path(output_path: Path) -> Path:
    return output_path.parent / f".tmp_{output_path.stem}.wav"


def get_checkpoint_path(output_path: Path) -> Path:
    return output_path.parent / f".checkpoint_{output_path.stem}.json"


# ============================================================
# Checkpoint / Resume
# ============================================================


def calculate_file_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            sha256.update(block)
    return sha256.hexdigest()


def save_checkpoint(
    checkpoint_path: Path,
    input_file: str,
    input_hash: str,
    voice_name: str,
    ref_audio: Path,
    ref_audio_hash: str,
    max_tokens: int,
    num_step: int,
    total_chunks: int,
    completed_chunks: list[int],
) -> None:
    data = {
        "file": Path(input_file).name,
        "file_hash": input_hash,
        "voice": voice_name,
        "ref_audio": str(ref_audio),
        "ref_audio_hash": ref_audio_hash,
        "max_tokens": max_tokens,
        "num_step": num_step,
        "total_chunks": total_chunks,
        "completed_chunks": sorted(completed_chunks),
        "timestamp": datetime.now().isoformat(),
        "version": "1.0",
    }
    checkpoint_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_checkpoint(checkpoint_path: Path) -> dict | None:
    if not checkpoint_path.exists():
        return None
    try:
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️  Failed to load checkpoint: {e}")
        return None


def verify_checkpoint(
    checkpoint: dict | None,
    input_file: str,
    input_hash: str,
    voice_name: str,
    ref_audio: Path,
    ref_audio_hash: str,
    max_tokens: int,
    num_step: int,
    total_chunks: int,
    output_path: Path,
) -> tuple[bool, list[int], str]:
    if not checkpoint:
        return False, [], "No checkpoint found"

    if checkpoint.get("file_hash") != input_hash:
        return False, [], "Input file has been modified since checkpoint"

    if checkpoint.get("voice") != voice_name:
        return False, [], "Voice changed since checkpoint"

    if checkpoint.get("ref_audio_hash") != ref_audio_hash:
        return False, [], "Voice sample has been modified since checkpoint"

    if checkpoint.get("max_tokens") != max_tokens:
        return False, [], "Max tokens changed since checkpoint"

    if checkpoint.get("num_step") != num_step:
        return False, [], "Diffusion steps changed since checkpoint"

    if checkpoint.get("total_chunks") != total_chunks:
        return False, [], "Chunk count changed since checkpoint"

    completed = checkpoint.get("completed_chunks")
    if not isinstance(completed, list):
        return False, [], "Invalid checkpoint format"

    valid_chunks = []
    for chunk_id in completed:
        chunk_path = get_chunk_path(output_path, chunk_id)
        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            valid_chunks.append(chunk_id)

    if not valid_chunks:
        return False, [], "No valid chunk files found on disk"

    return True, valid_chunks, f"Checkpoint valid ({len(valid_chunks)}/{total_chunks} chunks)"


# ============================================================
# WAV Operations
# ============================================================


def merge_wav_files(chunk_paths: list[Path], output_path: Path) -> None:
    if not chunk_paths:
        raise ValueError("No audio chunks to merge")

    with wave.open(str(chunk_paths[0]), "rb") as first_wav:
        params = first_wav.getparams()

    with wave.open(str(output_path), "wb") as final_wav:
        final_wav.setparams(params)
        for chunk_path in chunk_paths:
            with wave.open(str(chunk_path), "rb") as chunk_wav:
                # Compare format params only (not nframes — chunks have different durations)
                cp = chunk_wav
                if (cp.getnchannels() != params.nchannels
                        or cp.getsampwidth() != params.sampwidth
                        or cp.getframerate() != params.framerate):
                    raise ValueError(f"WAV format mismatch in {chunk_path}")
                final_wav.writeframes(cp.readframes(cp.getnframes()))


def write_wav(path: Path, audio) -> None:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise ImportError(
            "soundfile is required. Install with: pip install soundfile"
        ) from exc
    sf.write(str(path), audio, SAMPLE_RATE, subtype="PCM_16")


# ============================================================
# MP3 Conversion
# ============================================================


def wav_to_mp3(wav_path: Path, mp3_path: Path, overwrite: bool = False) -> None:
    if mp3_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {mp3_path}\n"
            f"Use --overwrite to replace it."
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav_path),
        "-codec:a", "libmp3lame",
        "-qscale:a", "2",
        str(mp3_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-500:]}"
        )


# ============================================================
# Model Loading
# ============================================================


def load_model(device: str | None, dtype_name: str):
    try:
        import torch
        from omnivoice import OmniVoice
    except ImportError as exc:
        raise ImportError(
            "OmniVoice dependencies are not available in this Python environment. "
            "Install with `pip install omnivoice torch torchaudio soundfile`, "
            "or run this script with the Python where `omnivoice-infer` is installed."
        ) from exc

    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }

    kwargs = {"dtype": dtype_map[dtype_name]}
    if device:
        kwargs["device_map"] = device

    return OmniVoice.from_pretrained("k2-fsa/OmniVoice", **kwargs)


def generate_audio(model, text: str, ref_audio, ref_text, args) -> object:
    kwargs = {
        "text": text,
        "ref_audio": str(ref_audio),
        "ref_text": ref_text,
        "num_step": args.num_step,
        "speed": args.speed,
    }

    if args.duration is not None:
        kwargs["duration"] = args.duration
    if args.language:
        kwargs["language"] = args.language

    audio = model.generate(**kwargs)
    if not audio:
        raise ValueError("OmniVoice returned no audio")
    return audio[0]


# ============================================================
# Input Reading
# ============================================================


def read_input_text(file_path: str, clean_md: bool) -> str:
    input_path = Path(file_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    raw_text = input_path.read_text(encoding="utf-8")
    text = clean_markdown(raw_text) if clean_md else raw_text.strip()
    if not text:
        raise ValueError("Input text is empty after cleaning")
    return text


# ============================================================
# Main Processing
# ============================================================


def process(voice_name: str, file_path: str, args) -> Path:
    count_tokens, split_into_chunks = load_text_chunker()

    # Resolve voice
    voice_dir = Path(args.voice_dir) if args.voice_dir else DEFAULT_VOICE_DIR
    ref_audio, ref_text = resolve_voice(voice_name, voice_dir)

    # Read input
    clean_text = read_input_text(file_path, args.markdown)

    # Output path
    output_path = Path(args.output) if args.output else get_default_output_path(file_path, voice_name)

    # Chunk
    total_tokens = count_tokens(clean_text)
    if total_tokens > args.max_tokens:
        chunks = split_into_chunks(clean_text, max_tokens=args.max_tokens)
    else:
        chunks = [clean_text]

    total_chunks = len(chunks)
    temp_wav = get_temp_wav_path(output_path)
    checkpoint_path = get_checkpoint_path(output_path)

    # Hashes for checkpoint validation
    input_hash = calculate_file_hash(Path(file_path))
    ref_audio_hash = calculate_file_hash(ref_audio)

    # Resume: check for existing checkpoint
    completed_set: set[int] = set()
    if args.resume:
        checkpoint = load_checkpoint(checkpoint_path)
        is_valid, valid_chunks, msg = verify_checkpoint(
            checkpoint, file_path, input_hash, voice_name,
            ref_audio, ref_audio_hash,
            args.max_tokens, args.num_step, total_chunks, output_path,
        )
        if is_valid:
            completed_set = set(valid_chunks)
            print(f"🔄 Resume: {len(completed_set)}/{total_chunks} chunks already done.")
        else:
            print(f"ℹ️  Resume skipped: {msg}. Starting fresh.")

    chunks_to_process = [
        (i, chunk) for i, chunk in enumerate(chunks, 1) if i not in completed_set
    ]

    print(f"\n{'=' * 60}")
    print("OmniVoice TTS Generator")
    print(f"{'=' * 60}")
    print(f"Input:  {file_path}")
    print(f"Output: {output_path}")
    print(f"Tokens: {total_tokens:,}")
    print(f"Chunks: {total_chunks} ({len(completed_set)} done, {len(chunks_to_process)} to generate)")
    print(f"Steps:  {args.num_step}")
    print(f"Device: {args.device or 'auto'}")

    if output_path.exists():
        if not args.overwrite:
            raise FileExistsError(
                f"Output file already exists: {output_path}\n"
                f"Use --overwrite to replace it."
            )
        print(f"⚠️  Overwriting: {output_path}")

    # Load model
    print("\nLoading OmniVoice model...")
    model = load_model(args.device, args.dtype)

    all_chunk_paths = [get_chunk_path(output_path, i) for i in range(1, total_chunks + 1)]

    # Generate chunks
    try:
        for index, chunk in chunks_to_process:
            chunk_path = get_chunk_path(output_path, index)
            print(f"\nGenerating chunk {index}/{total_chunks} ({count_tokens(chunk):,} tokens)...")
            audio = generate_audio(model, chunk, ref_audio, ref_text, args)
            write_wav(chunk_path, audio)
            completed_set.add(index)
            print(f"   ✅ Saved: {chunk_path.name}")

            # Save checkpoint after each chunk
            save_checkpoint(
                checkpoint_path, file_path, input_hash,
                voice_name, ref_audio, ref_audio_hash,
                args.max_tokens, args.num_step,
                total_chunks, list(completed_set),
            )

        # Assemble all chunks in order
        print(f"\n🔗 Assembling {total_chunks} chunks...")
        merge_wav_files(all_chunk_paths, temp_wav)
        print(f"   ✅ Merged WAV: {temp_wav.name}")
    except Exception:
        # Preserve checkpoint + chunk files on failure so --resume can continue later.
        raise

    # Convert to MP3 + cleanup temp WAV
    try:
        print("\n🎵 Converting to MP3...")
        wav_to_mp3(temp_wav, output_path, overwrite=True)
    finally:
        if not args.keep_wav:
            try:
                temp_wav.unlink()
            except OSError:
                pass

    # Clean up chunk temp files on success unless --keep-chunks
    if not args.keep_chunks:
        for cp in all_chunk_paths:
            try:
                cp.unlink()
            except OSError:
                pass

    # Clean up checkpoint on success
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"\n✅ Done: {output_path}")
    return output_path


# ============================================================
# CLI Parser
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OmniVoice TTS — generate MP3 from text/Markdown using voice cloning",
        usage="ov [voice] <file> [options]",
        epilog=(
            "Examples:\n"
            "  ov chapter.md                    # Use default voice (Kore)\n"
            "  ov Kore chapter.md               # Named voice\n"
            "  ov Minh chapter.md --num-step 50 # Custom steps\n"
            "  ov chapter.md --overwrite        # Overwrite existing output\n"
            "  ov chapter.md --resume           # Resume from checkpoint after error\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Positional: [voice] file
    parser.add_argument("positional1", nargs="?", metavar="[VOICE]", help="Voice name OR input file")
    parser.add_argument("positional2", nargs="?", metavar="<file>", help="Input file (when voice is specified)")

    # Output
    parser.add_argument("--output", "-o", help="Output MP3 path (default: <input>.mp3 next to input)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    parser.add_argument("--keep-wav", action="store_true", help="Keep intermediate WAV file")
    parser.add_argument("--keep-chunks", action="store_true", help="Keep intermediate chunk WAV files")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if available (skip completed chunks)")

    # Text processing
    parser.add_argument(
        "--no-markdown",
        dest="markdown",
        action="store_false",
        help="Do not clean Markdown formatting",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=MAX_TOKENS_PER_CHUNK,
        help=f"Maximum tokens per chunk (default: {MAX_TOKENS_PER_CHUNK})",
    )

    # Voice / model config
    parser.add_argument("--voice-dir", help=f"Voice samples directory (default: {DEFAULT_VOICE_DIR})")
    parser.add_argument("--language", default="vi", help="Language code (default: vi)")
    parser.add_argument("--device", default="mps", help="Device: mps, cuda:0, cpu (default: mps)")
    parser.add_argument(
        "--dtype",
        choices=["float16", "bfloat16", "float32"],
        default="float16",
        help="Model dtype (default: float16)",
    )
    parser.add_argument("--num-step", type=int, default=50, help="Diffusion steps (default: 50)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed factor (default: 1.0)")
    parser.add_argument("--duration", type=float, help="Fixed output duration in seconds")

    parser.set_defaults(markdown=True)
    return parser


def parse_positionals(args) -> tuple[str, str]:
    """
    Resolve positional args into (voice_name, file_path).

    Rules:
    - 2 args: (voice, file)
    - 1 arg that is a file: (default, file)
    - 1 arg that is not a file: treat as voice, require --text or error
    - 0 args: error
    """
    if args.positional1 is None:
        raise ValueError("No input specified.\nUsage: ov [voice] <file>")

    if args.positional2 is not None:
        # Two positionals: voice + file
        return args.positional1, args.positional2

    # One positional
    if Path(args.positional1).exists() and Path(args.positional1).is_file():
        return "default", args.positional1

    # Not a file → treat as voice name, but no file
    raise ValueError(
        f"'{args.positional1}' is not a file.\n"
        f"If it's a voice name, also provide a file: ov {args.positional1} <file>"
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.max_tokens < 1:
            raise ValueError("--max-tokens must be at least 1")

        voice_name, file_path = parse_positionals(args)
        process(voice_name, file_path, args)

    except Exception as exc:
        print(f"\n❌ Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

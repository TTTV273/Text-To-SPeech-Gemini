"""VieNeu-TTS Linux CPU generator.

Experimental TTS pipeline using the VieNeu-TTS v3 Turbo engine (torch-free
ONNX Runtime on CPU) instead of OmniVoice. Mirrors the CLI / chunk / checkpoint
/ merge behaviour of omnivoice_linux_generator.py so the two can be benchmarked
head-to-head.

Usage:
    vieneu-linux chapter.md
    vieneu-linux chapter.md --voice "Xuân Vĩnh"
    vieneu-linux chapter.md --ref-audio my_voice.wav
    vieneu-linux chapter.md --resume
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Bootstrap src/ into sys.path so `text_chunker` (and other src modules) resolve
# when this script is invoked directly without the vieneu-linux wrapper.
_SRC_DIR = Path(__file__).resolve().parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import omnivoice_generator as ov

DEFAULT_VOICE = "Bình An"
DEFAULT_MAX_TOKENS = 500
DEFAULT_TEMPERATURE = 0.8
DEFAULT_BACKEND = "onnx"


# ============================================================
# Checkpoint (VieNeu-specific fields)
# ============================================================


def save_checkpoint(
    checkpoint_path: Path,
    input_file: str,
    input_hash: str,
    voice: str,
    ref_audio: Path | None,
    ref_audio_hash: str,
    max_tokens: int,
    normalize_text: bool,
    temperature: float,
    total_chunks: int,
    completed_chunks: list[int],
) -> None:
    data = {
        "engine": "vieneu",
        "file": Path(input_file).name,
        "file_hash": input_hash,
        "voice": voice,
        "ref_audio": str(ref_audio) if ref_audio else None,
        "ref_audio_hash": ref_audio_hash,
        "max_tokens": max_tokens,
        "normalize_text": normalize_text,
        "temperature": temperature,
        "total_chunks": total_chunks,
        "completed_chunks": sorted(completed_chunks),
        "timestamp": datetime.now().isoformat(),
        "version": "1.0",
    }
    checkpoint_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def verify_checkpoint(
    checkpoint: dict | None,
    input_hash: str,
    voice: str,
    ref_audio_hash: str,
    max_tokens: int,
    normalize_text: bool,
    temperature: float,
    total_chunks: int,
    output_path: Path,
) -> tuple[bool, list[int], str]:
    if not checkpoint:
        return False, [], "No checkpoint found"

    if checkpoint.get("engine") != "vieneu":
        return False, [], "Checkpoint belongs to a different engine"

    if checkpoint.get("file_hash") != input_hash:
        return False, [], "Input file has been modified since checkpoint"

    if checkpoint.get("voice") != voice:
        return False, [], "Voice changed since checkpoint"

    if checkpoint.get("ref_audio_hash") != ref_audio_hash:
        return False, [], "Voice sample has been modified since checkpoint"

    if checkpoint.get("max_tokens") != max_tokens:
        return False, [], "Max tokens changed since checkpoint"

    if checkpoint.get("normalize_text", False) != normalize_text:
        return False, [], "Text normalization setting changed since checkpoint"

    if checkpoint.get("temperature") != temperature:
        return False, [], "Temperature changed since checkpoint"

    if checkpoint.get("total_chunks") != total_chunks:
        return False, [], "Chunk count changed since checkpoint"

    completed = checkpoint.get("completed_chunks")
    if not isinstance(completed, list):
        return False, [], "Invalid checkpoint format"

    valid_chunks = []
    for chunk_id in completed:
        chunk_path = ov.get_chunk_path(output_path, chunk_id)
        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            valid_chunks.append(chunk_id)

    if not valid_chunks:
        return False, [], "No valid chunk files found on disk"

    return True, valid_chunks, f"Checkpoint valid ({len(valid_chunks)}/{total_chunks} chunks)"


# ============================================================
# Model Loading
# ============================================================


def load_model(backend: str | None, temperature: float):
    """
    Load VieNeu-TTS engine.

    Args:
        backend: "onnx" (CPU torch-free, default) or "pytorch" (GPU).
        temperature: Sampling temperature for generation.

    Returns:
        Configured Vieneu instance.
    """
    try:
        from vieneu import Vieneu
    except ImportError as exc:
        raise ImportError(
            "VieNeu-TTS SDK is not available in this Python environment. "
            "Install CPU dependencies first:\n"
            "  pip install -r requirements-vieneu-linux.txt\n"
            "Or minimal SDK: pip install vieneu"
        ) from exc

    kwargs = {}
    if backend:
        kwargs["backend"] = backend

    return Vieneu(**kwargs)


def generate_audio(tts, text: str, voice: str | None, ref_audio: Path | None, temperature: float):
    """
    Generate audio for one chunk via VieNeu.

    Args:
        tts: Vieneu instance.
        text: Text to synthesize.
        voice: Preset voice name (None uses SDK default).
        ref_audio: Optional reference clip for zero-shot cloning.
        temperature: Sampling temperature.

    Returns:
        Audio object from tts.infer().
    """
    kwargs = {"text": text, "temperature": temperature}
    if ref_audio is not None:
        kwargs["ref_audio"] = str(ref_audio)
    elif voice is not None:
        kwargs["voice"] = voice

    return tts.infer(**kwargs)


# ============================================================
# Audio duration probe (for RTF benchmark)
# ============================================================


def probe_audio_seconds(path: Path) -> float | None:
    """Return audio duration in seconds via ffprobe, or None if unavailable."""
    if not shutil_which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired):
        pass
    return None


def shutil_which(cmd: str) -> str | None:
    import shutil
    return shutil.which(cmd)


# ============================================================
# Main Processing
# ============================================================


def process(file_path: str, args) -> Path:
    count_tokens, split_into_chunks = ov.load_text_chunker()

    # Read + clean input. VieNeu uses sea-g2p internally for phonemization,
    # so Vietnamese normalization defaults to OFF to avoid double-processing.
    clean_text = ov.read_input_text(file_path, args.markdown, args.normalize)

    # Resolve voice / cloning source
    ref_audio: Path | None = None
    ref_audio_for_hash: Path
    if args.ref_audio:
        ref_audio = Path(args.ref_audio)
        if not ref_audio.exists():
            raise FileNotFoundError(f"Reference audio not found: {ref_audio}")
        ref_audio_for_hash = ref_audio
        voice_label = f"clone({ref_audio.name})"
    else:
        ref_audio_for_hash = Path(file_path)  # stable placeholder hash source
        voice_label = args.voice

    # Output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = ov.get_default_output_path(file_path, "default")
        if args.voice != DEFAULT_VOICE and not args.ref_audio:
            output_path = output_path.with_name(
                f"{Path(file_path).stem}_{args.voice}.mp3"
            )

    # Chunk
    total_tokens = count_tokens(clean_text)
    if total_tokens > args.max_tokens:
        chunks = split_into_chunks(clean_text, max_tokens=args.max_tokens)
    else:
        chunks = [clean_text]

    total_chunks = len(chunks)
    temp_wav = ov.get_temp_wav_path(output_path)
    checkpoint_path = ov.get_checkpoint_path(output_path)

    input_hash = ov.calculate_file_hash(Path(file_path))
    ref_audio_hash = ov.calculate_file_hash(ref_audio_for_hash)

    # Resume
    completed_set: set[int] = set()
    if args.resume:
        checkpoint = ov.load_checkpoint(checkpoint_path)
        is_valid, valid_chunks, msg = verify_checkpoint(
            checkpoint, input_hash, voice_label, ref_audio_hash,
            args.max_tokens, args.normalize, args.temperature,
            total_chunks, output_path,
        )
        if is_valid:
            completed_set = set(valid_chunks)
            print(f"Resume: {len(completed_set)}/{total_chunks} chunks already done.")
        else:
            print(f"Resume skipped: {msg}. Starting fresh.")

    chunks_to_process = [
        (i, chunk) for i, chunk in enumerate(chunks, 1) if i not in completed_set
    ]

    print(f"\n{'=' * 60}")
    print("VieNeu-TTS Generator (Linux CPU)")
    print(f"{'=' * 60}")
    print(f"Input:   {file_path}")
    print(f"Output:  {output_path}")
    print(f"Voice:   {voice_label}")
    print(f"Backend: {args.backend}")
    print(f"Tokens:  {total_tokens:,}")
    print(f"Chunks:  {total_chunks} ({len(completed_set)} done, {len(chunks_to_process)} to generate)")
    print(f"Temp:    {args.temperature}")

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_path}\nUse --overwrite to replace it."
        )

    all_chunk_paths = [ov.get_chunk_path(output_path, i) for i in range(1, total_chunks + 1)]

    if not chunks_to_process:
        print("All chunks already complete; merging existing chunk files.")
    else:
        print("\nLoading VieNeu-TTS model...")
        t0 = time.time()
        tts = load_model(args.backend, args.temperature)
        load_seconds = time.time() - t0
        print(f"Model loaded in {load_seconds:.1f}s")

        chunk_times: list[float] = []
        for index, chunk in chunks_to_process:
            chunk_path = ov.get_chunk_path(output_path, index)
            print(
                f"\nGenerating chunk {index}/{total_chunks} "
                f"({count_tokens(chunk):,} tokens)..."
            )
            t1 = time.time()
            audio = generate_audio(tts, chunk, args.voice, ref_audio, args.temperature)
            tts.save(audio, str(chunk_path))
            elapsed = time.time() - t1
            chunk_times.append(elapsed)
            completed_set.add(index)
            print(f"   Saved: {chunk_path.name} ({elapsed:.1f}s)")

            save_checkpoint(
                checkpoint_path, file_path, input_hash,
                voice_label, ref_audio, ref_audio_hash,
                args.max_tokens, args.normalize, args.temperature,
                total_chunks, list(completed_set),
            )

    # Merge
    print(f"\nMerging {total_chunks} chunks...")
    merge_t0 = time.time()
    ov.merge_wav_files(all_chunk_paths, temp_wav)
    print(f"Merged WAV: {temp_wav.name} ({time.time() - merge_t0:.1f}s)")

    # Convert to MP3
    try:
        print("\nConverting to MP3...")
        ov.wav_to_mp3(temp_wav, output_path, overwrite=True)
    finally:
        if not args.keep_wav:
            try:
                temp_wav.unlink()
            except OSError:
                pass

    if not args.keep_chunks:
        for cp in all_chunk_paths:
            try:
                cp.unlink()
            except OSError:
                pass

    if checkpoint_path.exists():
        checkpoint_path.unlink()

    # Benchmark summary
    print(f"\nDone: {output_path}")
    total_wall = sum(chunk_times) if chunks_to_process else 0.0
    if chunk_times:
        print("\n--- Benchmark ---")
        print(f"Model load: {load_seconds:.1f}s")
        print(f"Generation: {total_wall:.1f}s ({len(chunk_times)} chunks)")
        print(f"Per chunk:  {total_wall / len(chunk_times):.1f}s avg")
        audio_dur = probe_audio_seconds(output_path)
        if audio_dur:
            rtf = total_wall / audio_dur if audio_dur > 0 else float("inf")
            print(f"Audio dur:  {audio_dur:.1f}s")
            print(f"RTF:        {rtf:.2f}  ({'faster' if rtf < 1 else 'slower'} than real-time)")

    return output_path


# ============================================================
# CLI
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VieNeu-TTS Linux CPU generator - generate MP3 from text/Markdown",
        usage="vieneu-linux <file> [options]",
        epilog=(
            "Examples:\n"
            "  vieneu-linux chapter.md\n"
            '  vieneu-linux chapter.md --voice "Xuân Vĩnh"\n'
            "  vieneu-linux chapter.md --ref-audio my_voice.wav\n"
            "  vieneu-linux chapter.md --resume\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("file", nargs="?", metavar="<file>", help="Input text/Markdown file")

    parser.add_argument("--output", "-o", help="Output MP3 path (default: <input>_<voice>.mp3)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    parser.add_argument("--keep-wav", action="store_true", help="Keep intermediate WAV file")
    parser.add_argument("--keep-chunks", action="store_true", help="Keep intermediate chunk WAV files")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if available")

    parser.add_argument(
        "--no-markdown",
        dest="markdown",
        action="store_false",
        help="Do not clean Markdown formatting",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Maximum tokens per chunk (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--normalize",
        dest="normalize",
        action="store_true",
        help=(
            "Run vietnormalizer before generation (OFF by default - VieNeu uses "
            "sea-g2p for phonemization internally)"
        ),
    )

    parser.add_argument(
        "--voice",
        default=None,
        help=f"Preset voice name (default: {DEFAULT_VOICE}). Use --list-voices to enumerate. "
             "Ignored when --ref-audio is given.",
    )
    parser.add_argument("--ref-audio", help="Reference clip (3-5s) for zero-shot voice cloning")
    parser.add_argument(
        "--backend",
        choices=["onnx", "pytorch"],
        default=DEFAULT_BACKEND,
        help=f"Inference backend (default: {DEFAULT_BACKEND} - torch-free CPU)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE})",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available preset voices and exit",
    )

    parser.set_defaults(markdown=True, normalize=False)
    return parser


def list_voices(tts) -> None:
    print("Available preset voices:")
    for label, voice_id in tts.list_preset_voices():
        print(f"  - {label} ({voice_id})")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.max_tokens < 1:
            raise ValueError("--max-tokens must be at least 1")
        if not (0.0 <= args.temperature <= 2.0):
            raise ValueError("--temperature must be between 0.0 and 2.0")
        if args.voice and args.ref_audio:
            raise ValueError("Use either --voice OR --ref-audio, not both")

        # Resolve effective voice label after mutual-exclusion check.
        effective_voice = args.voice or DEFAULT_VOICE
        args.voice = effective_voice

        if args.list_voices:
            tts = load_model(args.backend, args.temperature)
            list_voices(tts)
            return

        if not args.file:
            parser.error("the following arguments are required: <file>")

        process(args.file, args)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

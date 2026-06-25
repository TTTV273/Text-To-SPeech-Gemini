import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import omnivoice_generator as ov


DEFAULT_TORCH_THREADS = 16
DEFAULT_TORCH_INTEROP_THREADS = 1


def configure_torch_cpu_threads(torch_module, threads: int, interop_threads: int) -> None:
    """
    Configure PyTorch CPU threading before model loading/inference starts.

    Args:
        torch_module: Imported torch module.
        threads: Intra-op CPU thread count.
        interop_threads: Inter-op CPU thread count.
    """
    torch_module.set_num_threads(threads)
    torch_module.set_num_interop_threads(interop_threads)


def load_linux_model(device: str | None, dtype_name: str):
    """
    Load OmniVoice with Linux CPU-friendly defaults.

    Args:
        device: Device map for OmniVoice. Defaults to CPU in the parser.
        dtype_name: Model dtype name.

    Returns:
        OmniVoice model instance.
    """
    try:
        import torch
        from omnivoice import OmniVoice
    except ImportError as exc:
        raise ImportError(
            "OmniVoice Linux dependencies are not available in this Python environment. "
            "Use Python 3.11/3.12 and install CPU PyTorch first:\n"
            "  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install -r requirements-omnivoice-linux.txt"
        ) from exc

    threads = int(os.environ.get("OV_TORCH_THREADS", DEFAULT_TORCH_THREADS))
    interop_threads = int(os.environ.get("OV_TORCH_INTEROP_THREADS", DEFAULT_TORCH_INTEROP_THREADS))
    configure_torch_cpu_threads(torch, threads, interop_threads)

    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }

    if (device or "cpu") == "cpu" and dtype_name != "float32":
        print(
            "Warning: float32 is the recommended dtype for old Linux CPU/Xeon systems. "
            f"Requested dtype: {dtype_name}",
            file=sys.stderr,
        )

    kwargs = {"dtype": dtype_map[dtype_name]}
    if device:
        kwargs["device_map"] = device

    return OmniVoice.from_pretrained("k2-fsa/OmniVoice", **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OmniVoice Linux CPU TTS - generate MP3 from text/Markdown",
        usage="ov-linux [voice] <file> [options]",
        epilog=(
            "Examples:\n"
            "  ov-linux chapter.md\n"
            "  ov-linux Kore chapter.md\n"
            "  ov-linux chapter.md --torch-threads 8\n"
            "  ov-linux chapter.md --resume\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("positional1", nargs="?", metavar="[VOICE]", help="Voice name OR input file")
    parser.add_argument("positional2", nargs="?", metavar="<file>", help="Input file (when voice is specified)")

    parser.add_argument("--output", "-o", help="Output MP3 path (default: <input>.mp3 next to input)")
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
        default=ov.MAX_TOKENS_PER_CHUNK,
        help=f"Maximum tokens per chunk (default: {ov.MAX_TOKENS_PER_CHUNK})",
    )
    parser.add_argument(
        "--no-normalize",
        dest="normalize",
        action="store_false",
        help="Disable Vietnamese text normalization before OmniVoice generation",
    )

    parser.add_argument("--voice-dir", help=f"Voice samples directory (default: {ov.DEFAULT_VOICE_DIR})")
    parser.add_argument("--language", default="vi", help="Language code (default: vi)")
    parser.add_argument("--device", default="cpu", help="Device: cpu, cuda:0 (default: cpu)")
    parser.add_argument(
        "--dtype",
        choices=["float16", "bfloat16", "float32"],
        default="float32",
        help="Model dtype (default: float32)",
    )
    parser.add_argument("--num-step", type=int, default=16, help="Diffusion steps (default: 16)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed factor (default: 1.0)")
    parser.add_argument("--duration", type=float, help="Fixed output duration in seconds")
    parser.add_argument(
        "--torch-threads",
        type=int,
        default=int(os.environ.get("OV_TORCH_THREADS", DEFAULT_TORCH_THREADS)),
        help=f"PyTorch intra-op CPU threads (default: {DEFAULT_TORCH_THREADS})",
    )
    parser.add_argument(
        "--torch-interop-threads",
        type=int,
        default=int(os.environ.get("OV_TORCH_INTEROP_THREADS", DEFAULT_TORCH_INTEROP_THREADS)),
        help=f"PyTorch inter-op CPU threads (default: {DEFAULT_TORCH_INTEROP_THREADS})",
    )
    parser.add_argument(
        "--parallel-chunks",
        type=int,
        default=1,
        help="Number of parallel chunk workers, each pinned to a NUMA node (default: 1)",
    )
    parser.add_argument(
        "--_worker-chunks",
        default=None,
        help=argparse.SUPPRESS,
    )

    parser.set_defaults(markdown=True, normalize=True)
    return parser


def _run_worker(args) -> None:
    """Worker mode: generate specific chunks and write WAVs. No merge/MP3."""
    count_tokens, split_into_chunks = ov.load_text_chunker()

    voice_name, file_path = ov.parse_positionals(args)
    voice_dir = Path(args.voice_dir) if args.voice_dir else ov.DEFAULT_VOICE_DIR
    ref_audio, ref_text = ov.resolve_voice(voice_name, voice_dir)

    clean_text = ov.read_input_text(file_path, args.markdown, args.normalize)

    output_path = Path(args.output) if args.output else ov.get_default_output_path(file_path, voice_name)

    total_tokens = count_tokens(clean_text)
    if total_tokens > args.max_tokens:
        chunks = split_into_chunks(clean_text, max_tokens=args.max_tokens)
    else:
        chunks = [clean_text]

    assigned = sorted(int(x) for x in args._worker_chunks.split(","))
    print(f"[Worker] Chunks: {assigned}")

    model = load_linux_model(args.device, args.dtype)

    for index in assigned:
        chunk_text = chunks[index - 1]
        chunk_path = ov.get_chunk_path(output_path, index)
        print(f"[Worker] Generating chunk {index}/{len(chunks)} ({count_tokens(chunk_text):,} tokens)...")
        audio = ov.generate_audio(model, chunk_text, ref_audio, ref_text, args)
        ov.write_wav(chunk_path, audio)
        print(f"[Worker] Saved: {chunk_path.name}")


def _run_parallel(voice_name: str, file_path: str, args) -> Path:
    """Orchestrate parallel chunk generation across NUMA nodes."""
    count_tokens, split_into_chunks = ov.load_text_chunker()

    voice_dir = Path(args.voice_dir) if args.voice_dir else ov.DEFAULT_VOICE_DIR
    ref_audio, ref_text = ov.resolve_voice(voice_name, voice_dir)

    clean_text = ov.read_input_text(file_path, args.markdown, args.normalize)

    output_path = Path(args.output) if args.output else ov.get_default_output_path(file_path, voice_name)

    total_tokens = count_tokens(clean_text)
    if total_tokens > args.max_tokens:
        chunks = split_into_chunks(clean_text, max_tokens=args.max_tokens)
    else:
        chunks = [clean_text]

    total_chunks = len(chunks)
    if total_chunks < 2:
        print("Fewer than 2 chunks, falling back to sequential mode.")
        ov.load_model = load_linux_model
        return ov.process(voice_name, file_path, args)

    temp_wav = ov.get_temp_wav_path(output_path)
    checkpoint_path = ov.get_checkpoint_path(output_path)
    input_hash = ov.calculate_file_hash(Path(file_path))
    ref_audio_hash = ov.calculate_file_hash(ref_audio)

    # Resume
    completed_set: set[int] = set()
    if args.resume:
        checkpoint = ov.load_checkpoint(checkpoint_path)
        is_valid, valid_chunks, msg = ov.verify_checkpoint(
            checkpoint, file_path, input_hash, voice_name,
            ref_audio, ref_audio_hash,
            args.max_tokens, args.normalize, args.num_step, total_chunks, output_path,
        )
        if is_valid:
            completed_set = set(valid_chunks)
            print(f"Resume: {len(completed_set)}/{total_chunks} chunks already done.")
        else:
            print(f"Resume skipped: {msg}. Starting fresh.")

    chunks_to_process = [i for i in range(1, total_chunks + 1) if i not in completed_set]

    if not chunks_to_process:
        print("All chunks already complete.")
    else:
        if not shutil.which("numactl"):
            raise FileNotFoundError(
                "numactl is required for --parallel-chunks.\n"
                "Install with: sudo pacman -S numactl"
            )

        n_workers = args.parallel_chunks
        worker_threads = max(1, args.torch_threads // n_workers)

        node0_chunks = [i for idx, i in enumerate(chunks_to_process) if idx % 2 == 0]
        node1_chunks = [i for idx, i in enumerate(chunks_to_process) if idx % 2 == 1]

        print(f"\n{'=' * 60}")
        print("OmniVoice TTS Generator (Parallel Chunks)")
        print(f"{'=' * 60}")
        print(f"Input:  {file_path}")
        print(f"Output: {output_path}")
        print(f"Tokens: {total_tokens:,}")
        print(f"Chunks: {total_chunks} ({len(completed_set)} done, {len(chunks_to_process)} to generate)")
        print(f"Steps:  {args.num_step}")
        print(f"Workers: {n_workers} x {worker_threads} threads")
        print(f"  Node 0: chunks {node0_chunks}")
        print(f"  Node 1: chunks {node1_chunks}")

        if output_path.exists() and not args.overwrite:
            raise FileExistsError(
                f"Output file already exists: {output_path}\nUse --overwrite to replace it."
            )

        python = sys.executable
        script = str(Path(__file__).resolve())

        workers: list[tuple[int, subprocess.Popen]] = []
        for node, node_chunks in [(0, node0_chunks), (1, node1_chunks)]:
            if not node_chunks:
                continue
            chunks_str = ",".join(str(i) for i in node_chunks)
            cmd = [
                "numactl", f"--cpunodebind={node}", f"--membind={node}",
                python, script,
                voice_name, file_path,
                f"--_worker-chunks={chunks_str}",
                f"--torch-threads={worker_threads}",
                f"--num-step={args.num_step}",
                f"--max-tokens={args.max_tokens}",
                f"--device=cpu",
                f"--dtype={args.dtype}",
                f"--language={args.language}",
                f"--speed={args.speed}",
            ]
            if args.output:
                cmd.append(f"--output={args.output}")
            if args.voice_dir:
                cmd.append(f"--voice-dir={args.voice_dir}")
            if not args.markdown:
                cmd.append("--no-markdown")
            if not args.normalize:
                cmd.append("--no-normalize")
            if args.duration is not None:
                cmd.append(f"--duration={args.duration}")

            env = os.environ.copy()
            env["OMP_NUM_THREADS"] = str(worker_threads)
            env["MKL_NUM_THREADS"] = str(worker_threads)
            env["OV_TORCH_THREADS"] = str(worker_threads)

            print(f"\nLaunching node {node} worker ({len(node_chunks)} chunks)...")
            proc = subprocess.Popen(cmd, env=env)
            workers.append((node, proc))

        # Wait for all workers
        failed = False
        for node, proc in workers:
            ret = proc.wait()
            if ret != 0:
                print(f"Node {node} worker FAILED (exit {ret})")
                failed = True
            else:
                print(f"Node {node} worker completed.")

        if failed:
            for index in chunks_to_process:
                chunk_path = ov.get_chunk_path(output_path, index)
                if chunk_path.exists() and chunk_path.stat().st_size > 0:
                    completed_set.add(index)
            ov.save_checkpoint(
                checkpoint_path, file_path, input_hash,
                voice_name, ref_audio, ref_audio_hash,
                args.max_tokens, args.normalize, args.num_step,
                total_chunks, list(completed_set),
            )
            raise RuntimeError("Some workers failed. Checkpoint saved. Use --resume to retry.")

        completed_set.update(chunks_to_process)

    # Merge + convert
    all_chunk_paths = [ov.get_chunk_path(output_path, i) for i in range(1, total_chunks + 1)]

    missing = [cp for cp in all_chunk_paths if not cp.exists() or cp.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Missing chunk files: {[cp.name for cp in missing]}")

    print(f"\nMerging {total_chunks} chunks...")
    ov.merge_wav_files(all_chunk_paths, temp_wav)
    print(f"Merged WAV: {temp_wav.name}")

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

    print(f"\nDone: {output_path}")
    return output_path


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.max_tokens < 1:
            raise ValueError("--max-tokens must be at least 1")
        if args.torch_threads < 1:
            raise ValueError("--torch-threads must be at least 1")
        if args.torch_interop_threads < 1:
            raise ValueError("--torch-interop-threads must be at least 1")

        os.environ["OV_TORCH_THREADS"] = str(args.torch_threads)
        os.environ["OV_TORCH_INTEROP_THREADS"] = str(args.torch_interop_threads)
        os.environ.setdefault("OMP_NUM_THREADS", str(args.torch_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(args.torch_threads))

        if args._worker_chunks is not None:
            _run_worker(args)
        elif args.parallel_chunks > 1:
            voice_name, file_path = ov.parse_positionals(args)
            _run_parallel(voice_name, file_path, args)
        else:
            print("Linux CPU runtime:")
            print(f"  Device: {args.device}")
            print(f"  Dtype: {args.dtype}")
            print(f"  Torch threads: {args.torch_threads}")
            print(f"  Torch inter-op threads: {args.torch_interop_threads}")
            print(f"  OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS')}")
            print(f"  MKL_NUM_THREADS: {os.environ.get('MKL_NUM_THREADS')}")

            ov.load_model = load_linux_model
            voice_name, file_path = ov.parse_positionals(args)
            ov.process(voice_name, file_path, args)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

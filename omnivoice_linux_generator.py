import argparse
import os
import sys

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

    parser.set_defaults(markdown=True, normalize=True)
    return parser


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

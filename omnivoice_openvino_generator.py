#!/usr/bin/env python3
"""OmniVoice TTS using OpenVINO IR for CPU inference on Linux.

Reuses CLI/logic from omnivoice_linux_generator but replaces the PyTorch
forward pass with an OpenVINO compiled model for faster CPU inference.

Usage:
    .venv-omnivoice/bin/python omnivoice_openvino_generator.py chapter.md
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_SRC_DIR = str(Path(__file__).parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import numpy as np
import torch

import openvino as ov
import omnivoice_generator as ov_gen
import omnivoice_linux_generator as ov_linux

_MODEL_DIR = Path(__file__).parent / "models" / "openvino"
_W8A8_MODEL = _MODEL_DIR / "omnivoice_lm_w8a8" / "model.xml"
_FP32_MODEL = _MODEL_DIR / "omnivoice_lm_fp32" / "model.xml"
DEFAULT_OPENVINO_MODEL = _W8A8_MODEL if _W8A8_MODEL.exists() else _FP32_MODEL


@dataclass
class _ModelOutput:
    """Mimics OmniVoiceModelOutput.logits for the calling code."""
    logits: torch.Tensor


def _make_openvino_forward(compiled_model):
    """Return a forward(self, ...) that delegates to OpenVINO."""
    infer_request = compiled_model.create_infer_request()

    def openvino_forward(self, input_ids, audio_mask, attention_mask, **kwargs):
        input_ids_np = input_ids.detach().cpu().to(torch.int64).numpy()
        audio_mask_np = audio_mask.detach().cpu().to(torch.bool).numpy()
        attention_mask_np = attention_mask.detach().cpu().to(torch.bool).numpy()

        infer_request.infer(
            [
                ov.Tensor(input_ids_np),
                ov.Tensor(audio_mask_np),
                ov.Tensor(attention_mask_np),
            ]
        )

        output = infer_request.get_output_tensor(0)
        logits = torch.from_numpy(output.data)

        return _ModelOutput(logits=logits)

    return openvino_forward


def load_openvino_model(device, dtype_name, openvino_path, threads):
    """Load OmniVoice (for tokenizers/audio) + OpenVINO compiled model."""
    from omnivoice import OmniVoice

    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        dtype=torch.float32,
        device_map="cpu",
        attn_implementation="eager",
    )
    model.eval()

    core = ov.Core()
    core.set_property(
        "CPU",
        {
            "INFERENCE_NUM_THREADS": str(threads),
            "INFERENCE_PRECISION_HINT": "f32",
        },
    )

    ov_model = core.read_model(str(openvino_path))
    compiled = core.compile_model(ov_model, "CPU")

    import types

    model.forward = types.MethodType(_make_openvino_forward(compiled), model)

    return model


def build_parser():
    parser = ov_linux.build_parser()
    parser.description = "OmniVoice OpenVINO TTS - generate MP3 from text/Markdown"
    parser.prog = "ov-openvino"

    parser.add_argument(
        "--openvino-model",
        default=str(DEFAULT_OPENVINO_MODEL),
        help=f"Path to OpenVINO IR .xml (default: {DEFAULT_OPENVINO_MODEL})",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.max_tokens < 1:
            raise ValueError("--max-tokens must be at least 1")
        if args.torch_threads < 1:
            raise ValueError("--torch-threads must be at least 1")

        os.environ.setdefault("OMP_NUM_THREADS", str(args.torch_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(args.torch_threads))

        openvino_path = Path(args.openvino_model)
        if not openvino_path.exists():
            raise FileNotFoundError(
                f"OpenVINO model not found: {openvino_path}\n"
                "Run: python scripts/convert_omnivoice_openvino.py"
            )

        print("OpenVINO runtime:")
        print(f"  Device: {args.device}")
        print(f"  Dtype: {args.dtype}")
        print(f"  Threads: {args.torch_threads}")
        print(f"  OpenVINO model: {openvino_path}")

        def custom_load_model(device, dtype_name):
            return load_openvino_model(
                device, dtype_name, openvino_path, args.torch_threads
            )

        ov_gen.load_model = custom_load_model

        voice_name, file_path = ov_gen.parse_positionals(args)
        ov_gen.process(voice_name, file_path, args)

    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Quantize OmniVoice OpenVINO FP32 model to INT8 (W8A8) using NNCF.

Uses a small calibration set generated from the real OmniVoice inference
pipeline with the default voice sample.

Usage:
    .venv-omnivoice/bin/python scripts/quantize_omnivoice_openvino.py
"""

import sys
from pathlib import Path

import numpy as np
import torch
import openvino as ov
import nncf

from omnivoice import OmniVoice

NUM_AUDIO_CODEBOOK = 8
AUDIO_VOCAB_SIZE = 1025
FP32_MODEL = Path("models/openvino/omnivoice_lm_fp32/model.xml")
OUTPUT_DIR = Path("models/openvino/omnivoice_lm_w8a8")

CALIBRATION_TEXTS = [
    "Xin chào, đây là đoạn thử nghiệm ngắn.",
    "Luân Xa Thời Gian xoay chuyển, các Thời Đại đến rồi đi.",
    "Hôm nay trời đẹp, chúng ta hãy đi dạo trong công viên.",
    "Người ta thường nói rằng cuộc sống là một hành trình dài.",
    "Khoa học công nghệ đang phát triển với tốc độ chóng mặt.",
]


def generate_calibration_data(model):
    """Generate realistic calibration inputs from the OmniVoice pipeline."""
    ref_audio = "voices/default/Kore.MP3"
    ref_text = "CHƯƠNG 1. Những Hạt Giống của Bóng Tối."

    voice_clone_prompt = model.create_voice_clone_prompt(
        ref_audio=ref_audio, ref_text=ref_text
    )

    samples = []
    for text in CALIBRATION_TEXTS:
        task = model._preprocess_all(
            text=text,
            language="vi",
            ref_text=voice_clone_prompt.ref_text,
            ref_audio=voice_clone_prompt.ref_audio_tokens,
            voice_clone_prompt=voice_clone_prompt,
        )

        inputs_list = [
            model._prepare_inference_inputs(
                task.texts[i],
                task.target_lens[i],
                task.ref_texts[i],
                task.ref_audio_tokens[i],
                task.langs[i],
                task.instructs[i],
                denoise=True,
            )
            for i in range(task.batch_size)
        ]

        B = task.batch_size
        c_lens = [inp["input_ids"].size(2) for inp in inputs_list]
        max_c_len = max(c_lens)
        pad_id = model.config.audio_mask_id

        batch_input_ids = torch.full(
            (2 * B, NUM_AUDIO_CODEBOOK, max_c_len), pad_id, dtype=torch.long
        )
        batch_audio_mask = torch.zeros((2 * B, max_c_len), dtype=torch.bool)
        batch_attention_mask = torch.zeros(
            (2 * B, 1, max_c_len, max_c_len), dtype=torch.bool
        )

        for i, inp in enumerate(inputs_list):
            c_len, u_len = c_lens[i], task.target_lens[i]
            batch_input_ids[i, :, :c_len] = inp["input_ids"]
            batch_audio_mask[i, :c_len] = inp["audio_mask"]
            batch_attention_mask[i, :, :c_len, :c_len] = True
            batch_input_ids[B + i, :, :u_len] = inp["input_ids"][..., -u_len:]
            batch_audio_mask[B + i, :u_len] = inp["audio_mask"][..., -u_len:]
            batch_attention_mask[B + i, :, :u_len, :u_len] = True
            if max_c_len > u_len:
                pad_diag = torch.arange(u_len, max_c_len)
                batch_attention_mask[B + i, :, pad_diag, pad_diag] = True

        samples.append(
            {
                "input_ids": batch_input_ids.cpu().to(torch.int64).numpy(),
                "audio_mask": batch_audio_mask.cpu().to(torch.bool).numpy(),
                "attention_mask": batch_attention_mask.cpu().to(torch.bool).numpy(),
            }
        )

    return samples


def main():
    print("Loading OmniVoice model for calibration...")
    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        dtype=torch.float32,
        device_map="cpu",
        attn_implementation="eager",
    )
    model.eval()

    print(f"Generating {len(CALIBRATION_TEXTS)} calibration samples...")
    calib_data = generate_calibration_data(model)

    print(f"Loading FP32 OpenVINO model: {FP32_MODEL}")
    core = ov.Core()
    ov_model = core.read_model(str(FP32_MODEL))

    input_names = [inp.any_name for inp in ov_model.inputs]
    print(f"Model inputs: {input_names}")

    dataset = nncf.Dataset(calib_data, lambda x: x)

    print("Running NNCF W8A8 quantization (this may take 10-30 minutes)...")
    quantized = nncf.quantize(
        ov_model,
        dataset,
        preset=nncf.QuantizationPreset.MIXED,
        subset_size=len(calib_data),
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "model.xml"
    ov.save_model(quantized, str(output_path))
    print(f"Saved W8A8 model to {output_path}")


if __name__ == "__main__":
    main()

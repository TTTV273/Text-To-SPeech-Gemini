#!/usr/bin/env python3
"""Convert OmniVoice forward path to OpenVINO IR (FP32).

Converts the full inference forward path:
  input_ids + audio_mask + attention_mask -> audio_logits

This covers embeddings, LLM (Qwen3 backbone), and audio_heads in a single
OpenVINO graph so the runtime can optimise end-to-end.

Usage:
    .venv-omnivoice/bin/python scripts/convert_omnivoice_openvino.py
"""

import sys
from pathlib import Path

import torch
import torch.nn as nn

import openvino as ov
from omnivoice import OmniVoice


NUM_AUDIO_CODEBOOK = 8
AUDIO_VOCAB_SIZE = 1025
HIDDEN_SIZE = 1024


class OmniVoiceForwardWrapper(nn.Module):
    """Thin wrapper exposing only the inference forward path."""

    def __init__(self, model: OmniVoice):
        super().__init__()
        self.llm = model.llm
        self.audio_embeddings = model.audio_embeddings
        self.audio_heads = model.audio_heads
        self.register_buffer(
            "codebook_layer_offsets", model.codebook_layer_offsets
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        audio_mask: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        # --- _prepare_embed_inputs ---
        text_embeds = self.llm.get_input_embeddings()(input_ids[:, 0, :])

        shifted_ids = (
            input_ids * audio_mask.unsqueeze(1)
        ) + self.codebook_layer_offsets.view(1, -1, 1)
        audio_embeds = self.audio_embeddings(shifted_ids).sum(dim=1)
        inputs_embeds = torch.where(
            audio_mask.unsqueeze(-1), audio_embeds, text_embeds
        )

        # --- LLM forward ---
        # Convert 4D bool mask to 4D additive float mask for SDPA.
        # True = attend (0.0), False = mask (-inf)
        float_attn_mask = torch.where(
            attention_mask,
            torch.zeros((), dtype=torch.float32),
            torch.full((), torch.finfo(torch.float32).min, dtype=torch.float32),
        )

        llm_outputs = self.llm(
            inputs_embeds=inputs_embeds,
            attention_mask=float_attn_mask,
            return_dict=True,
            use_cache=False,
        )
        hidden_states = llm_outputs[0]

        # --- audio heads ---
        batch_size, seq_len, _ = hidden_states.shape
        logits_flat = self.audio_heads(hidden_states)
        audio_logits = logits_flat.view(
            batch_size, seq_len, NUM_AUDIO_CODEBOOK, AUDIO_VOCAB_SIZE
        ).permute(0, 2, 1, 3)

        return audio_logits


def main():
    print("Loading OmniVoice model (FP32, CPU, eager attention)...")
    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        dtype=torch.float32,
        device_map="cpu",
        attn_implementation="eager",
    )
    model.eval()

    wrapper = OmniVoiceForwardWrapper(model)
    wrapper.eval()

    # Example inputs: B=1 → 2*B=2 (conditional + unconditional)
    B = 1
    seq_len = 128

    example_input_ids = torch.randint(
        0, AUDIO_VOCAB_SIZE, (2 * B, NUM_AUDIO_CODEBOOK, seq_len), dtype=torch.long
    )
    example_audio_mask = torch.zeros(2 * B, seq_len, dtype=torch.bool)
    example_audio_mask[:, -50:] = True
    example_attention_mask = torch.ones(
        2 * B, 1, seq_len, seq_len, dtype=torch.bool
    )

    print("Converting to OpenVINO IR (this may take several minutes)...")
    try:
        ov_model = ov.convert_model(
            wrapper,
            example_input=[
                example_input_ids,
                example_audio_mask,
                example_attention_mask,
            ],
        )
    except Exception as exc:
        print(f"Direct convert_model failed: {exc}", file=sys.stderr)
        print("Trying torch.export path...", file=sys.stderr)
        exported = torch.export.export(
            wrapper,
            (example_input_ids, example_audio_mask, example_attention_mask),
        )
        ov_model = ov.convert_model(exported)

    output_dir = Path("models/openvino/omnivoice_lm_fp32")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "model.xml"
    ov.save_model(ov_model, str(output_path))
    print(f"Saved OpenVINO IR to {output_path}")


if __name__ == "__main__":
    main()

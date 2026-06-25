import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omnivoice_generator import read_input_text, verify_checkpoint


class OmniVoiceGeneratorTests(unittest.TestCase):
    def test_read_input_text_normalizes_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "chapter.md"
            input_path.write_text("# Title\n\nHôm nay là 25/12/2023", encoding="utf-8")

            with patch(
                "omnivoice_generator.normalize_vietnamese_text",
                return_value="normalized text",
            ) as mock_normalize:
                result = read_input_text(str(input_path), clean_md=True, normalize_text=True)

        self.assertEqual(result, "normalized text")
        mock_normalize.assert_called_once_with("Title\n\nHôm nay là 25/12/2023")

    def test_read_input_text_skips_normalization_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "chapter.md"
            input_path.write_text("# Title\n\nHôm nay là 25/12/2023", encoding="utf-8")

            with patch("omnivoice_generator.normalize_vietnamese_text") as mock_normalize:
                result = read_input_text(str(input_path), clean_md=True, normalize_text=False)

        self.assertEqual(result, "Title\n\nHôm nay là 25/12/2023")
        mock_normalize.assert_not_called()

    def test_verify_checkpoint_rejects_changed_normalize_setting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            input_path = base_path / "chapter.md"
            ref_audio = base_path / "voice.wav"
            output_path = base_path / "chapter.mp3"
            chunk_path = base_path / ".chunk_1_chapter.wav"

            input_path.write_text("xin chao", encoding="utf-8")
            ref_audio.write_bytes(b"voice")
            chunk_path.write_bytes(b"chunk")

            checkpoint = {
                "file_hash": "input-hash",
                "voice": "default",
                "ref_audio_hash": "ref-hash",
                "max_tokens": 500,
                "normalize_text": False,
                "num_step": 50,
                "total_chunks": 1,
                "completed_chunks": [1],
            }

            is_valid, valid_chunks, message = verify_checkpoint(
                checkpoint,
                str(input_path),
                "input-hash",
                "default",
                ref_audio,
                "ref-hash",
                500,
                True,
                50,
                1,
                output_path,
            )

        self.assertFalse(is_valid)
        self.assertEqual(valid_chunks, [])
        self.assertEqual(message, "Text normalization setting changed since checkpoint")


if __name__ == "__main__":
    unittest.main()

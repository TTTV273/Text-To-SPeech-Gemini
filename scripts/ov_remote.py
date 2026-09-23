#!/usr/bin/env python3
"""
OmniVoice Remote CLI Client

Sends text or markdown files from your local Mac to a remote OmniVoice GPU server
(e.g., Google Colab with Cloudflare Tunnel), tracks real-time progress,
and downloads the generated audiobook (MP3/WAV) to your local disk.

Usage:
    ./ov-remote chapter.md
    ./ov-remote chapter.md Kore
    ./ov-remote chapter.md --voice Kore --speed 1.1 --output TTS/output/ch1.mp3
    ./ov-remote --set-server https://xxxx.trycloudflare.com
    ./ov-remote --health
    ./ov-remote --list-voices
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ 'requests' is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / ".ov_server_url"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "TTS" / "output"


def get_stored_server_url() -> Optional[str]:
    """Retrieve server URL from environment variable or local config file."""
    env_url = os.environ.get("OMNIVOICE_SERVER_URL")
    if env_url:
        return env_url.strip().rstrip("/")
    if CONFIG_FILE.exists():
        url = CONFIG_FILE.read_text(encoding="utf-8").strip()
        if url:
            return url.rstrip("/")
    return None


def save_server_url(url: str):
    """Save server URL to config file for future use."""
    clean_url = url.strip().rstrip("/")
    CONFIG_FILE.write_text(clean_url, encoding="utf-8")
    print(f"✅ Saved default server URL: {clean_url}")


def render_progress_bar(percent: float, message: str, width: int = 30) -> str:
    """Render a text progress bar."""
    percent = max(0.0, min(100.0, percent))
    filled = int(width * (percent / 100.0))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:5.1f}% | {message}"


def check_health(server_url: str) -> bool:
    """Check if server is reachable and print GPU status."""
    try:
        resp = requests.get(f"{server_url}/health", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        gpu = data.get("gpu", {})
        print("=" * 60)
        print("🌐 Remote Server Status: ONLINE")
        print(f"🔗 Server URL: {server_url}")
        if gpu.get("available"):
            print(f"⚡ GPU: {gpu.get('device_name')} ({gpu.get('memory_total_gb', 0)} GB VRAM)")
        else:
            print("⚠️  Running on CPU (Slow)")
        print(f"📦 Model Cached: {'Yes' if data.get('model_loaded') else 'No (loads on 1st request)'}")
        print(f"🕒 Pending Queue: {data.get('queue_size', 0)} tasks")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"❌ Failed to connect to server at {server_url}: {e}", file=sys.stderr)
        return False


def list_voices(server_url: str):
    """Fetch available voices from server."""
    try:
        resp = requests.get(f"{server_url}/api/voices", timeout=10)
        resp.raise_for_status()
        voices = resp.json().get("voices", [])
        print("\n🎙️  Available Remote Voices:")
        for v in voices:
            print(f"  • {v}")
        print()
    except Exception as e:
        print(f"❌ Could not fetch voices: {e}", file=sys.stderr)


def get_local_voice_sample(voice_name: str) -> tuple[Optional[Path], Optional[str]]:
    """Find voice audio and text in local voices directory on Mac."""
    voice_dir = PROJECT_ROOT / "voices"
    target_folder = voice_dir / ("default" if voice_name == "default" else voice_name)

    if target_folder.exists():
        audio_file = None
        for ext in [".wav", ".mp3", ".MP3", ".m4a", ".flac"]:
            candidates = list(target_folder.glob(f"*{ext}"))
            if candidates:
                audio_file = candidates[0]
                break

        txt_candidates = list(target_folder.glob("*.txt"))
        if audio_file and txt_candidates:
            ref_text = txt_candidates[0].read_text(encoding="utf-8").strip()
            return audio_file, ref_text

    return None, None


def submit_and_track(
    server_url: str,
    file_path: Path,
    voice: str,
    speed: float,
    num_step: int,
    output_format: str,
    output_path: Path,
    max_tokens: int,
    normalize: bool,
    markdown: bool,
    poll_interval: float = 1.5,
):
    """Upload file to server, track progress, and download output."""
    if not file_path.exists():
        print(f"❌ Input file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n🚀 Sending '{file_path.name}' to remote GPU...")
    print(f"   Voice: {voice} | Speed: {speed} | Steps: {num_step} | Format: {output_format.upper()}")

    # Find voice files locally to upload if needed
    local_voice_audio, local_voice_text = get_local_voice_sample(voice)
    if local_voice_audio and local_voice_text:
        print(f"🎙️  Attaching voice '{voice}' ({local_voice_audio.name}, {local_voice_audio.stat().st_size / 1024:.1f} KB)")

    # 1. Upload & create task
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "text/plain")}
            data = {
                "filename": file_path.stem,
                "voice": voice,
                "speed": speed,
                "num_step": num_step,
                "output_format": output_format,
                "max_tokens": max_tokens,
                "normalize": normalize,
                "markdown": markdown,
            }

            if local_voice_audio and local_voice_text:
                with open(local_voice_audio, "rb") as f_voice:
                    files["ref_audio_file"] = (local_voice_audio.name, f_voice, "application/octet-stream")
                    data["ref_text"] = local_voice_text
                    resp = requests.post(f"{server_url}/api/tts", files=files, data=data, timeout=60)
            else:
                resp = requests.post(f"{server_url}/api/tts", files=files, data=data, timeout=60)

            resp.raise_for_status()
            task_info = resp.json()
    except requests.exceptions.RequestException as exc:
        print(f"❌ Failed to submit task to server: {exc}", file=sys.stderr)
        sys.exit(1)

    task_id = task_info["task_id"]
    print(f"📋 Task Created! ID: [{task_id}] (Queue pos: {task_info.get('position_in_queue', 1)})")
    print("⏳ Processing on remote GPU...\n")

    # 2. Polling progress
    last_msg = ""
    start_time = time.time()
    try:
        while True:
            try:
                stat_resp = requests.get(f"{server_url}/api/tasks/{task_id}", timeout=15)
                stat_resp.raise_for_status()
                task = stat_resp.json()
            except requests.exceptions.RequestException:
                time.sleep(poll_interval)
                continue

            status = task.get("status")
            progress = task.get("progress", {})
            percent = float(progress.get("percent", 0.0))
            msg = progress.get("message", "Processing...")

            # Format progress line
            bar_line = render_progress_bar(percent, msg)
            sys.stdout.write(f"\r{bar_line.ljust(80)}")
            sys.stdout.flush()

            if status == "COMPLETED":
                sys.stdout.write("\n")
                break
            elif status == "FAILED":
                sys.stdout.write("\n")
                print(f"\n❌ Remote Task Failed: {task.get('error')}", file=sys.stderr)
                sys.exit(1)

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user. Remote task is still running on server.")
        sys.exit(130)

    elapsed = time.time() - start_time
    print(f"✅ Audio generated in {elapsed:.1f}s! Downloading file...")

    # 3. Download output audio
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(f"{server_url}/api/tasks/{task_id}/download", stream=True, timeout=60) as dl_resp:
            dl_resp.raise_for_status()
            total_bytes = 0
            with open(output_path, "wb") as f_out:
                for chunk in dl_resp.iter_content(chunk_size=16384):
                    if chunk:
                        f_out.write(chunk)
                        total_bytes += len(chunk)

        print(f"🎉 Saved successfully: {output_path} ({total_bytes / (1024 * 1024):.2f} MB)")

        # 4. Cleanup task on server
        try:
            requests.delete(f"{server_url}/api/tasks/{task_id}", timeout=5)
        except Exception:
            pass

    except Exception as dl_err:
        print(f"❌ Failed to download audio: {dl_err}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OmniVoice Remote CLI — Generate speech via remote GPU (Colab)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("file_or_voice", nargs="?", help="Input markdown/text file, or voice name if 2 positional args given")
    parser.add_argument("file_optional", nargs="?", help="Input file if first arg was voice name")

    parser.add_argument("--server", help="Server URL (e.g. https://xxxx.trycloudflare.com)")
    parser.add_argument("--set-server", metavar="URL", help="Save server URL as default and exit")
    parser.add_argument("--health", action="store_true", help="Check server health & GPU status and exit")
    parser.add_argument("--list-voices", action="store_true", help="List available voices on server and exit")

    parser.add_argument("-v", "--voice", default=None, help="Voice name (default: default / Kore)")
    parser.add_argument("-o", "--output", help="Output file path (default: TTS/output/<stem>.<format>)")
    parser.add_argument("--format", choices=["mp3", "wav"], default="mp3", help="Output format (default: mp3)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (default: 1.0)")
    parser.add_argument("--num-step", type=int, default=32, help="Inference diffusion steps (default: 32)")
    parser.add_argument("--max-tokens", type=int, default=500, help="Max tokens per chunk (default: 500)")
    parser.add_argument("--no-normalize", dest="normalize", action="store_false", default=True, help="Disable Vietnamese normalization")
    parser.add_argument("--no-markdown", dest="markdown", action="store_false", default=True, help="Disable Markdown cleaning")
    return parser


def parse_positionals(args) -> tuple[Optional[str], Optional[Path]]:
    """Support both: ov-remote file.md [voice] and ov-remote [voice] file.md"""
    a = args.file_or_voice
    b = args.file_optional

    voice = args.voice
    file_path = None

    if a and b:
        # Check which one is a file
        pa, pb = Path(a), Path(b)
        if pa.exists():
            file_path = pa
            voice = voice or b
        elif pb.exists():
            file_path = pb
            voice = voice or a
        else:
            # Assume first is voice, second is file path
            voice = voice or a
            file_path = pb
    elif a:
        pa = Path(a)
        if pa.exists() or pa.suffix in [".md", ".txt"]:
            file_path = pa
        else:
            # Maybe it's a voice name without a file?
            voice = voice or a

    return voice or "default", file_path


def main():
    parser = build_parser()
    args = parser.parse_args()

    # 1. Handle --set-server
    if args.set_server:
        save_server_url(args.set_server)
        return

    # 2. Resolve Server URL
    server_url = args.server or get_stored_server_url()
    if not server_url:
        print("❌ Server URL is not configured!", file=sys.stderr)
        print("👉 Run: ./ov-remote --set-server https://xxxx.trycloudflare.com", file=sys.stderr)
        print("   or provide: ./ov-remote file.md --server https://xxxx.trycloudflare.com", file=sys.stderr)
        sys.exit(1)

    # 3. Handle info flags
    if args.health:
        check_health(server_url)
        return

    if args.list_voices:
        list_voices(server_url)
        return

    # 4. Resolve input file and voice
    voice, file_path = parse_positionals(args)
    if not file_path:
        parser.print_help()
        sys.exit(1)

    # 5. Resolve output path
    if args.output:
        out_path = Path(args.output)
        if out_path.is_dir():
            out_path = out_path / f"{file_path.stem}_{voice}.{args.format}"
    else:
        out_path = DEFAULT_OUTPUT_DIR / f"{file_path.stem}_{voice}.{args.format}"

    # 6. Run generation
    submit_and_track(
        server_url=server_url,
        file_path=file_path,
        voice=voice,
        speed=args.speed,
        num_step=args.num_step,
        output_format=args.format,
        output_path=out_path,
        max_tokens=args.max_tokens,
        normalize=args.normalize,
        markdown=args.markdown,
    )


if __name__ == "__main__":
    main()

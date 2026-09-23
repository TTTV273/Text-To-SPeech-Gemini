#!/usr/bin/env python3
"""
OmniVoice Colab Server (FastAPI + Background Queue + Cloudflare Tunnel)

Allows running OmniVoice TTS on Google Colab GPU and serving requests
from a local machine via a secure public tunnel.

Usage on Colab:
    python scripts/colab_server.py --port 8000 --tunnel
"""

import argparse
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# Global state
app = FastAPI(title="OmniVoice TTS Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TASK_QUEUE: queue.Queue = queue.Queue()
TASKS: dict[str, dict] = {}
MODEL_CACHE = {"model": None, "device": None, "dtype": None}
CACHE_DIR = PROJECT_ROOT / "TTS" / "server_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class DummyArgs:
    num_step: int = 32
    speed: float = 1.0
    duration: Optional[float] = None
    language: Optional[str] = None


def get_gpu_info() -> dict:
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "available": True,
                "device_name": torch.cuda.get_device_name(0),
                "device_count": torch.cuda.device_count(),
                "memory_total_gb": round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2),
            }
    except Exception:
        pass
    return {"available": False, "device_name": "CPU", "device_count": 0, "memory_total_gb": 0}


def get_cached_model():
    """Load and cache OmniVoice model on GPU/CPU."""
    import torch
    from omnivoice_generator import load_model

    if MODEL_CACHE["model"] is None:
        device = "cuda" if torch.cuda.is_available() else None
        dtype = "float16" if torch.cuda.is_available() else "float32"
        print(f"📦 Loading OmniVoice model into memory (device={device or 'cpu'}, dtype={dtype})...")
        t0 = time.time()
        MODEL_CACHE["model"] = load_model(device, dtype)
        MODEL_CACHE["device"] = device
        MODEL_CACHE["dtype"] = dtype
        print(f"✅ Model loaded successfully in {time.time() - t0:.2f}s!")
    return MODEL_CACHE["model"]


def worker_loop():
    """Sequential worker to process TTS tasks without VRAM exhaustion."""
    while True:
        task_data = TASK_QUEUE.get()
        if task_data is None:
            break

        task_id = task_data["task_id"]
        TASKS[task_id]["status"] = "PROCESSING"
        TASKS[task_id]["started_at"] = time.time()

        try:
            from omnivoice_generator import (
                clean_markdown,
                generate_audio,
                get_chunk_path,
                load_text_chunker,
                merge_wav_files,
                normalize_vietnamese_text,
                resolve_voice,
                wav_to_mp3,
                write_wav,
            )

            text = task_data["text"]
            voice_name = task_data["voice"]
            speed = task_data["speed"]
            num_step = task_data["num_step"]
            output_format = task_data["output_format"]
            max_tokens = task_data["max_tokens"]
            do_normalize = task_data["normalize"]
            do_markdown = task_data["markdown"]

            task_dir = CACHE_DIR / task_id
            task_dir.mkdir(parents=True, exist_ok=True)

            # 1. Clean markdown
            if do_markdown:
                text = clean_markdown(text)

            # 2. Vietnamese normalization
            if do_normalize:
                try:
                    text = normalize_vietnamese_text(text)
                except Exception as norm_err:
                    print(f"⚠️ Normalization warning: {norm_err}")

            # 3. Chunk text
            count_tokens, split_into_chunks = load_text_chunker()
            total_tokens = count_tokens(text)
            if total_tokens > max_tokens:
                chunks = split_into_chunks(text, max_tokens=max_tokens)
            else:
                chunks = [text]

            total_chunks = len(chunks)
            TASKS[task_id]["progress"] = {
                "current": 0,
                "total": total_chunks,
                "percent": 0.0,
                "message": f"Splitted into {total_chunks} chunks ({total_tokens:,} tokens)",
            }

            # 4. Resolve voice
            voice_dir = PROJECT_ROOT / "voices"
            ref_audio, ref_text = resolve_voice(voice_name, voice_dir)

            # 5. Load model & prepare args
            model = get_cached_model()
            args = DummyArgs(num_step=num_step, speed=speed)

            # 6. Generate chunks
            chunk_paths = []
            for i, chunk in enumerate(chunks, 1):
                TASKS[task_id]["progress"] = {
                    "current": i,
                    "total": total_chunks,
                    "percent": round(((i - 1) / total_chunks) * 100, 1),
                    "message": f"Generating chunk {i}/{total_chunks} ({count_tokens(chunk):,} tokens)...",
                }

                chunk_wav = task_dir / f"chunk_{i:04d}.wav"
                audio = generate_audio(model, chunk, ref_audio, ref_text, args)
                write_wav(chunk_wav, audio)
                chunk_paths.append(chunk_wav)

            # 7. Merge and convert
            TASKS[task_id]["progress"] = {
                "current": total_chunks,
                "total": total_chunks,
                "percent": 95.0,
                "message": "Merging audio chunks and finalizing...",
            }

            merged_wav = task_dir / "output.wav"
            merge_wav_files(chunk_paths, merged_wav)

            if output_format.lower() == "mp3":
                final_file = task_dir / "output.mp3"
                wav_to_mp3(merged_wav, final_file, overwrite=True)
                try:
                    merged_wav.unlink()
                except OSError:
                    pass
            else:
                final_file = merged_wav

            TASKS[task_id]["status"] = "COMPLETED"
            TASKS[task_id]["output_file"] = str(final_file)
            TASKS[task_id]["completed_at"] = time.time()
            TASKS[task_id]["progress"] = {
                "current": total_chunks,
                "total": total_chunks,
                "percent": 100.0,
                "message": "Finished successfully!",
            }
            print(f"🎉 Task {task_id} completed: {final_file.name}")

        except Exception as exc:
            import traceback
            traceback.print_exc()
            TASKS[task_id]["status"] = "FAILED"
            TASKS[task_id]["error"] = str(exc)
            TASKS[task_id]["completed_at"] = time.time()
        finally:
            TASK_QUEUE.task_done()


# Start background worker thread
worker_thread = threading.Thread(target=worker_loop, daemon=True)
worker_thread.start()


# ============================================================
# API Endpoints
# ============================================================


@app.get("/")
@app.get("/health")
def health():
    gpu_info = get_gpu_info()
    return {
        "status": "online",
        "service": "OmniVoice TTS Server",
        "gpu": gpu_info,
        "queue_size": TASK_QUEUE.qsize(),
        "model_loaded": MODEL_CACHE["model"] is not None,
    }


@app.get("/api/voices")
def list_voices():
    voice_dir = PROJECT_ROOT / "voices"
    voices = []
    if voice_dir.exists():
        for d in sorted(voice_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                voices.append(d.name)
    if "default" not in voices:
        voices.insert(0, "default")
    return {"voices": voices}


@app.post("/api/tts")
async def create_tts_task(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    filename: Optional[str] = Form("audiobook"),
    voice: str = Form("default"),
    speed: float = Form(1.0),
    num_step: int = Form(32),
    output_format: str = Form("mp3"),
    max_tokens: int = Form(500),
    normalize: bool = Form(True),
    markdown: bool = Form(True),
):
    if file is not None:
        content_bytes = await file.read()
        raw_text = content_bytes.decode("utf-8", errors="ignore")
        if not filename or filename == "audiobook":
            filename = Path(file.filename or "audiobook").stem
    elif text:
        raw_text = text
    else:
        raise HTTPException(status_code=400, detail="Either 'file' or 'text' must be provided.")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Input text is empty.")

    task_id = str(uuid.uuid4())[:8]
    TASKS[task_id] = {
        "task_id": task_id,
        "filename": filename,
        "status": "QUEUED",
        "voice": voice,
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "output_file": None,
        "error": None,
        "progress": {"current": 0, "total": 0, "percent": 0.0, "message": "Queued in worker"},
    }

    TASK_QUEUE.put({
        "task_id": task_id,
        "text": raw_text,
        "filename": filename,
        "voice": voice,
        "speed": speed,
        "num_step": num_step,
        "output_format": output_format,
        "max_tokens": max_tokens,
        "normalize": normalize,
        "markdown": markdown,
    })

    return {
        "task_id": task_id,
        "status": "QUEUED",
        "position_in_queue": TASK_QUEUE.qsize(),
    }


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return TASKS[task_id]


@app.get("/api/tasks/{task_id}/download")
def download_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")

    task = TASKS[task_id]
    if task["status"] != "COMPLETED" or not task.get("output_file"):
        raise HTTPException(status_code=400, detail=f"Task is {task['status']}, file not ready.")

    file_path = Path(task["output_file"])
    if not file_path.exists():
        raise HTTPException(status_code=410, detail="Generated audio file no longer exists.")

    ext = file_path.suffix.lstrip(".")
    media_type = "audio/mpeg" if ext == "mp3" else "audio/wav"
    download_name = f"{task.get('filename', 'audio')}.{ext}"

    return FileResponse(file_path, media_type=media_type, filename=download_name)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    task_dir = CACHE_DIR / task_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)
    del TASKS[task_id]
    return {"message": f"Task {task_id} cleaned up."}


# ============================================================
# Cloudflare Tunnel Helper
# ============================================================


def start_cloudflare_tunnel(port: int) -> Optional[str]:
    """Start cloudflared quick tunnel and return public URL."""
    cloudflared_path = shutil.which("cloudflared")

    if not cloudflared_path:
        # Check /tmp/cloudflared or /usr/local/bin/cloudflared
        for candidate in ["/usr/local/bin/cloudflared", "/tmp/cloudflared"]:
            if Path(candidate).is_file() and os.access(candidate, os.X_OK):
                cloudflared_path = candidate
                break

    if not cloudflared_path:
        print("📥 Downloading cloudflared binary for Linux...")
        dl_target = Path("/tmp/cloudflared")
        cmd = [
            "curl", "-sL",
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
            "-o", str(dl_target)
        ]
        res = subprocess.run(cmd)
        if res.returncode == 0:
            dl_target.chmod(0o755)
            cloudflared_path = str(dl_target)
        else:
            print("❌ Failed to download cloudflared.")
            return None

    print(f"🌐 Starting Cloudflare Tunnel for port {port}...")
    log_file = CACHE_DIR / "cloudflared.log"
    with open(log_file, "w") as f:
        proc = subprocess.Popen(
            [cloudflared_path, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=f,
            stderr=subprocess.STDOUT,
        )

    # Poll log file for trycloudflare URL
    tunnel_url = None
    for _ in range(30):
        time.sleep(1)
        if log_file.exists():
            content = log_file.read_text()
            matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
            if matches:
                tunnel_url = matches[0]
                break

    return tunnel_url


def main():
    parser = argparse.ArgumentParser(description="OmniVoice Colab Server")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--tunnel", action="store_true", help="Launch Cloudflare quick tunnel")
    parser.add_argument("--preload", action="store_true", help="Preload model immediately on startup")
    args = parser.parse_args()

    # Preload model if requested or on Colab
    if args.preload or os.environ.get("COLAB_GPU"):
        get_cached_model()

    tunnel_url = None
    if args.tunnel:
        tunnel_url = start_cloudflare_tunnel(args.port)

    print("\n" + "=" * 64)
    print("🚀 OmniVoice TTS Server is ready!")
    print(f"🏠 Local URL:   http://127.0.0.1:{args.port}")
    if tunnel_url:
        print(f"🔗 Public URL:  {tunnel_url}")
        print("\n👉 Use this URL on your Mac with: ./ov-remote --set-server " + tunnel_url)
    print("=" * 64 + "\n")

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

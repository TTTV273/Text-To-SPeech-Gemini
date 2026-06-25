# Running OmniVoice on Your Linux Machine

## Executive verdict

For your exact machine, the best practical route is **CPU-first OmniVoice with aggressive thread and NUMA tuning**, not CUDA. The GPU path is effectively closed because your Quadro K4000 is a **Kepler, compute capability 3.0** card, while modern PyTorch releases used by current OmniVoice installs target much newer CUDA stacks and architectures; current PyTorch release notes list supported Linux x86 CUDA architectures starting at **Maxwell 5.0** for CUDA 12.6 builds, and NVIDIA’s legacy GPU table places older Kepler boards in the legacy CC list, far below that floor. OmniVoice itself is a modern package that requires **Python >= 3.10** and **torch >= 2.4**, and its repository currently constrains the preferred install path around **torch 2.8.0 / torchaudio 2.8.0**, which makes “old PyTorch + Kepler CUDA” a mismatch with the current codebase rather than a clean deployment option. citeturn19view0turn20search0turn28search5turn28search6

The single most important conclusion is this: on a dual-socket Xeon E5-2670 system, **the maintainable speed path is to optimize CPU execution**, then consider **OpenVINO** if you are willing to use a more experimental path, and only then look at **community GGUF/GGML ports**. I would *not* spend time on IPEX for this box, and I would *not* try to resurrect Kepler CUDA for OmniVoice unless the goal is purely experimental. That recommendation is an inference from OmniVoice’s package requirements, PyTorch’s current compatibility matrix, Intel’s current IPEX status, and the capabilities of your Sandy Bridge-era Xeons. citeturn20search0turn19view0turn15search9turn15search12turn42search0

A second practical issue is your Python version. OmniVoice’s package metadata allows **torch >= 2.4**, but the repository’s tested constraints are on **torch 2.8.0**, and PyTorch 2.8 supports **Python 3.9–3.13**, while PyTorch 2.12 is the first line in the current matrix that includes **Python 3.14**. So your current system Python 3.14 is *not ideal* for the repo’s preferred pinned setup. The safest deployment for OmniVoice today is a dedicated **Python 3.12 or 3.13 venv** for the official PyTorch/OmniVoice path. citeturn20search0turn19view0

## What your hardware means in practice

Your CPUs are first-generation Xeon E5-2670 parts. Intel’s own specs list the E5-2670 instruction set extensions as **Intel AVX**, not AVX2, AVX-512, or AMX. That matters because almost every “special” modern CPU acceleration story for deep learning on Intel hardware leans heavily on **AVX-512**, **AVX-512 VNNI**, **AVX-512 BF16**, or **AMX**. Your platform predates all of those. In other words, you have lots of cores and enough RAM, but you do **not** have the vector ISA features that make BF16- and INT8-heavy Intel acceleration especially compelling. citeturn42search0turn15search0turn41search0

That is why **`bfloat16` is not likely to help you**. Intel’s and PyTorch’s BF16 performance discussions are centered on newer Xeons with AVX-512 BF16 and AMX support, and IPEX itself advertises optimizations built around AVX-512 VNNI and AMX. On an AVX-only Sandy Bridge Xeon, BF16 support may exist in software pathways in some stacks, but it should not be expected to outperform well-tuned FP32 inference, and it may even be slower because the hardware lacks the fast BF16 execution features these optimizations were designed for. For your machine, **`float32` is the correct default**, and BF16 should be treated as a low-probability experiment rather than a recommended mode. citeturn41search0turn41search1turn15search0turn42search0

Your dual-socket layout is still valuable. Intel’s own tuning guide notes that NUMA can strongly affect performance, that cross-socket memory access is slower than local memory access, and that `numactl` can be used to bind CPU execution and memory allocation to a given socket. That makes your machine a good fit for **coarse-grained parallelism** across audiobook chunks, especially because your workload is embarrassingly parallel at the chapter/segment level. citeturn32view0turn31search0

## How to get the most out of CPU mode

PyTorch does not force you to accept its default thread behavior. The core knobs are **intra-op threads** through `torch.set_num_threads()`, **inter-op threads** through `torch.set_num_interop_threads()`, and the environment variables **`OMP_NUM_THREADS`** and **`MKL_NUM_THREADS`**. PyTorch’s docs say `torch.set_num_threads()` controls the number of threads used for **intra-op CPU parallelism** and should be called **before** running eager, JIT, or autograd code, while `torch.set_num_interop_threads()` controls **inter-op** parallelism and can only be set once before inter-op work starts. PyTorch’s threading environment docs also state that `MKL_NUM_THREADS` controls Intel MKL thread count and **takes precedence over `OMP_NUM_THREADS`**. citeturn6view1turn11view1turn43view0turn43view1turn43view2

For a **single OmniVoice process**, the best starting point on your machine is **not 32 threads**. Intel’s PyTorch tuning guide explicitly says that on dual-socket Xeon systems, it is typically better to avoid logical cores for good performance, and it describes `OMP_NUM_THREADS` defaults in terms of physical cores. On your host that strongly suggests starting with **16 threads total**, not 32, because you have 16 physical cores across two sockets. In practice, the most sensible first benchmark grid is: **8 threads**, **16 threads**, and then **32 threads only as a check**, because some workloads benefit slightly from SMT while others slow down due to contention. For a diffusion-style TTS workload with repeated matrix-heavy kernels, **16** is the most likely winner. citeturn32view0turn6view1

For **two parallel OmniVoice processes**, one per socket, PyTorch’s multiprocessing guidance becomes very relevant. The docs warn that CPU oversubscription can destroy efficiency, and recommend sizing threads per process as roughly **`floor(N / M)`** where *N* is available CPU capacity and *M* is the number of subprocesses. On paper you could treat *N* as 32 logical CPUs and use 16 threads per process, but Intel’s own guidance to avoid logical cores for best performance makes **2 processes × 8 threads each** the better first configuration on your hardware. This is the layout I would test first for audiobook chunking. citeturn11view2turn11view4turn32view0

The NUMA-aware version of that plan is straightforward:

```bash
# Process on NUMA node 0
OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
numactl --cpunodebind=0 --membind=0 \
python omnivoice_generator.py chunk_A.md --device cpu --dtype float32

# Process on NUMA node 1
OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
numactl --cpunodebind=1 --membind=1 \
python omnivoice_generator.py chunk_B.md --device cpu --dtype float32
```

That command style matches the `numactl` behavior described in the Linux man page and in Intel’s tuning guide, which specifically recommends binding execution and memory to local sockets to avoid cross-socket traffic. Before hard-coding CPU IDs, use `lscpu` or `numactl --hardware` to verify your node topology, because the exact logical-core numbering on old dual-socket boards is not always the same as users expect. citeturn31search0turn32view0

Two additional tuning knobs are worth trying. First, if you switch from GNU OpenMP to Intel’s `libiomp`, Intel notes that `KMP_AFFINITY` can have a **dramatic** effect on speed, though this is an advanced tuning path and not something I would do before you have baseline numbers. Second, Intel’s guide notes that oneDNN primitive caching can matter for transformer- and speech-like workloads with dynamic shapes; if your text chunks vary a lot in length, increasing `ONEDNN_PRIMITIVE_CACHE_CAPACITY` may help after warmup, at the cost of memory. Neither is a guaranteed win on Sandy Bridge, but both are more plausible than BF16 or IPEX on this box. citeturn32view0

A good **single-process baseline launcher** for your machine is:

```python
import torch

torch.set_num_threads(16)
torch.set_num_interop_threads(1)  # keep inter-op low for a single inference process
```

and then run with:

```bash
OMP_NUM_THREADS=16 MKL_NUM_THREADS=16 python omnivoice_generator.py input.md --device cpu --dtype float32
```

PyTorch’s APIs and threading docs support this configuration style directly. citeturn6view1turn11view1turn43view0

## Which acceleration paths are actually worth trying

The only non-PyTorch acceleration path that currently looks genuinely promising for OmniVoice on CPU is **OpenVINO**. OpenVINO explicitly supports conversion of PyTorch `nn.Module`, TorchScript, and `torch.export` artifacts via `openvino.convert_model`, and its docs recommend supplying `example_input` for better correctness and performance. OpenVINO also accepts ONNX as a backup conversion route, though its docs say that converting through ONNX is more expensive and should be considered a fallback if direct conversion does not work. citeturn13view2

More importantly, there is already a directly relevant OmniVoice data point from the project’s own issue tracker. In May 2026, a contributor reported OpenVINO CPU experiments for OmniVoice and summarized results showing **OpenVINO FP32 matching PyTorch/ONNX FP32**, while an **OpenVINO W8A8** path on a modern Intel i7-14700 reached about **2.1× faster** than FP32 in the fastest tested setting. The same contributor said their earlier **ONNX/GGUF** experiments gave only more modest gains compared with OpenVINO. That is not your CPU, and the author explicitly warns that speedups may be smaller on older Intel or AMD chips, but it is the best publicly documented OmniVoice-specific CPU optimization evidence available right now. citeturn26view0turn26view2

So the right way to rank acceleration options on your machine is:

- **Official PyTorch CPU path**: lowest risk, easiest to maintain, almost certain to work. citeturn20search0
- **OpenVINO conversion path**: highest upside on CPU if conversion succeeds, but more engineering work and not yet a simple official OmniVoice path. citeturn13view2turn26view0
- **Community GGUF/GGML path**: potentially attractive for memory footprint and deployment simplicity, but still unofficial and not proven to match the Python reference path closely in all cases. citeturn22view4turn22view3

For your machine specifically, I would treat OpenVINO as a **Phase Two optimization project**, not the first thing to do. The reasons are practical: OpenVINO supports Python 3.10–3.14, but its current validated deep-learning framework versions list **PyTorch 2.4** and **ONNX 1.16**, while OmniVoice documentation today is centered on **torch 2.8.0**. That does not mean OpenVINO cannot work with OmniVoice; it means you should expect some compatibility testing and potentially a dedicated environment just for conversion and runtime. citeturn13view3turn20search0

## Which paths are mostly dead ends

### IPEX

IPEX is not a good bet for this host. Intel has **discontinued active development** after the 2.8 release and separately states that IPEX reached **end of life by the end of March 2026**, advising users to prefer native PyTorch going forward. In addition, IPEX’s own packaging is focused on modern Intel acceleration features such as **AVX-512 VNNI** and **AMX**, and its published wheels on PyPI stop at **CPython 3.13** on Linux — there is **no cp314 wheel** on the current 2.8.0 release page. On top of that, even friendly downstream documentation describes IPEX as optimized for **AVX-512 or above**, with benefits on older CPUs “not guaranteed.” Your Xeon E5-2670 is older still, with only plain AVX. citeturn15search9turn15search12turn17view1turn17view4turn41search7turn42search0

The short version is that **IPEX + Python 3.14 + Sandy Bridge Xeon** is the wrong intersection of technologies. It is possible you could force an older 3.12/3.13 environment and benchmark it, but I would only do that if you have already exhausted PyTorch CPU tuning and OpenVINO. citeturn17view1turn15search12turn41search7

### Old PyTorch with CUDA 10.2 for Kepler

This is theoretically interesting and operationally wrong for your goal. OmniVoice’s package metadata requires **torch >= 2.4**, and the repo’s preferred install path is pinned around **torch 2.8.0 / torchaudio 2.8.0**. PyTorch’s release matrix shows that the **1.x line** tops out at much older Python and CUDA combinations, and the modern 2.x lines have moved to CUDA 11.7+ and now 12.x. Even if you could source-build an ancient PyTorch against CUDA 10.2 for Kepler, you would still be outside the dependency floor and testing surface of current OmniVoice. This makes it a maintenance project, not a deployment strategy. citeturn20search0turn19view0

This is also why your GPU problem is not just “PyTorch binaries are mean to old cards.” It is a stack-level mismatch: **legacy Kepler GPU**, **legacy driver branch**, **legacy compatible CUDA toolchain**, versus a **current diffusion TTS codebase** built around recent PyTorch releases. For real work, that stack is no longer worth rehabilitating. citeturn19view0turn28search5turn28search6

### Native PyTorch quantization as a full OmniVoice solution

PyTorch quantization is real, but the operator coverage story matters. PyTorch’s quantization reference explicitly shows that **dynamic quantization** has first-class modules such as **Linear** and **LSTM**, and also notes that quantized tensors support only a **limited subset** of regular tensor operations. That is a warning sign for a complex diffusion-style TTS pipeline with custom components, dynamic shapes, and nontrivial audio/token stages. In other words, some submodules may be quantizable, but “apply `torch.quantization` and get a fast full-model INT8 OmniVoice” is unlikely to be plug-and-play. citeturn25view0turn25view1turn25view2

### bitsandbytes on CPU as the main answer

bitsandbytes now has non-CUDA backend work, but the official Hugging Face docs still describe that support as a **preview alpha release**, explicitly warning that bugs are expected and performance may not meet expectations. The same docs say Intel CPU and AMD ROCm are considered functional in the alpha, but bitsandbytes remains fundamentally an LLM-centric k-bit quantization toolkit, not an OmniVoice-specific acceleration path. It is worth watching, not betting your audiobook pipeline on. citeturn22view0turn22view1

## Community paths that may become useful

A community **GGML/GGUF** route for OmniVoice now exists. The OmniVoice issue tracker includes an early **`omnivoice.cpp`** experiment described as a standalone C++ implementation using GGML, with CPU fallback and OmniVoice-compatible GGUF files, but the author is very explicit that it is **not an official replacement**, that parity with the Python/PyTorch path is **not fully proven**, and that tokenizer/quantization/conversion details may still change. citeturn22view4

Separately, a Hugging Face model repository for **OmniVoice GGUF** now advertises quantized weights for `omnivoice.cpp`, with CPU/CUDA/ROCm/Metal/Vulkan backends and model variants ranging from **Q4_K_M** up through **F32**. The published file sizes are attractive for old hardware — for example, the base model is listed at roughly **407 MB in Q4_K_M**, **656 MB in Q8_0**, and **1.23 GB in BF16** — and that makes this route interesting for your 32 GB RAM system even without any viable GPU. But because this is a community port rather than the official k2-fsa runtime, I would treat it as an **experimental third option** after official PyTorch CPU and OpenVINO. citeturn22view3

This matters because your use case is long-form audiobook generation with resume/checkpoint support. Stability and output consistency matter more than shaving every last second. The GGUF path is promising precisely because it may eventually become the best answer for old CPUs, but today its own public status still says “early,” not “production replacement.” citeturn22view4turn22view3

## Better alternatives if CPU throughput matters more than OmniVoice

If the real priority is **fast local Vietnamese TTS on CPU**, and especially if you can live without OmniVoice’s broad multilingual zero-shot voice cloning strengths, then **Sherpa-ONNX** and **Piper** deserve serious attention.

Sherpa-ONNX is specifically designed around **offline ONNX-runtime-based speech workloads** across Linux, macOS, Windows, embedded systems, and x86_64 servers, and its official TTS model list includes **Vietnamese** among supported monolingual languages. The Sherpa-ONNX project also already supports multiple TTS engines in its ecosystem, including **Kokoro**, **Piper**, and **VITS**. For a machine like yours, that combination — ONNX runtime, CPU-friendly deployment, and explicit Vietnamese TTS support — makes Sherpa-ONNX the strongest “lighter than OmniVoice” candidate. citeturn35view0turn35view1

Piper is another strong fit for your hardware profile. Its repository describes Piper as **a fast, local neural text-to-speech system**, and the official voice list includes **Vietnamese** voices such as `25hours_single`, `vais1000`, and `vivos`. Piper is much closer to a classic offline TTS appliance than OmniVoice: easier to deploy, lighter on CPU, and far better aligned with “turn markdown into speech quickly on old hardware.” What you give up is OmniVoice’s newer zero-shot multilingual voice-cloning style capability. citeturn38search3turn39view0

By contrast, two options you mentioned are currently poor matches for Vietnamese in their official upstream form. **XTTS-v2** officially supports **17 languages**, and Vietnamese is **not** on that list. **MeloTTS** upstream officially supports **English, Spanish, French, Chinese, Japanese, and Korean**, also excluding Vietnamese in the mainline project. There are community forks and fine-tunes for Vietnamese around both ecosystems, but upstream official support today is the more reliable yardstick, and by that yardstick neither is the clean answer for your use case. citeturn35view2turn35view4

**Kokoro** is attractive for raw efficiency because the official model is only **82 million parameters** and is marketed as significantly faster and more cost-efficient than larger TTS models. But the official Kokoro repo’s documented language codes currently enumerate American/British English, Spanish, French, Hindi, Italian, Japanese, Brazilian Portuguese, and Mandarin Chinese; Vietnamese is not part of the core official language list there, even though the underlying **Misaki** G2P project now has a Vietnamese section and the broader ecosystem is clearly moving in that direction. So Kokoro is promising, but for **Vietnamese today** I would not place it ahead of Sherpa-ONNX or Piper unless you are willing to use community fine-tunes and do your own validation. citeturn35view3turn37view3turn37view4

## Recommended deployment plan

My recommendation, in order, is:

First, create a **dedicated Python 3.12 or 3.13 environment** for OmniVoice, because that aligns with the repo’s preferred 2.8-era PyTorch setup much better than system Python 3.14. Then run the official **CPU FP32** path and benchmark it with three thread configurations: **8**, **16**, and **32**. Do that before touching anything else, because it will tell you whether the model is compute-bound, memory-bound, or oversubscribed on your host. citeturn20search0turn19view0turn32view0

Second, if your goal is maximum wall-clock throughput for audiobook generation, split work at the **chapter or chunk level** and run **two independent OmniVoice CPU processes**, each pinned to one NUMA node with **8 threads** and local memory binding. That is the best match between PyTorch’s oversubscription guidance and Intel’s recommendation to avoid leaning on logical cores unnecessarily. This is the most likely configuration to outperform a single 16-thread process once you have many independent chunks queued. citeturn11view2turn11view4turn32view0turn31search0

Third, if the official CPU path is still too slow, invest engineering time in **OpenVINO**, not IPEX. The evidence is not universal, but it is the only path with a documented OmniVoice-specific report of materially better CPU performance than PyTorch/ONNX, and it is much more aligned with current inference tooling than reviving IPEX or Kepler CUDA. citeturn26view0turn13view2turn15search12

Fourth, if you decide that “local, cheap, fast Vietnamese audiobook generation” matters more than “OmniVoice specifically,” pivot to **Sherpa-ONNX** or **Piper**. Those two are the best-supported CPU-oriented Vietnamese alternatives in the sources reviewed here. OmniVoice remains the richer multilingual zero-shot/cloning platform, but it is not the easiest fit for your aging workstation. citeturn35view0turn35view1turn39view0

If I reduce everything above to one operational answer, it is this:

```bash
# safest baseline
OMP_NUM_THREADS=16 MKL_NUM_THREADS=16 \
python omnivoice_generator.py input.md --device cpu --dtype float32
```

Then benchmark this dual-socket version for batch audiobook work:

```bash
# socket 0
OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
numactl --cpunodebind=0 --membind=0 \
python omnivoice_generator.py part1.md --device cpu --dtype float32

# socket 1
OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
numactl --cpunodebind=1 --membind=1 \
python omnivoice_generator.py part2.md --device cpu --dtype float32
```

On *your* hardware, that is the highest-confidence path to “fastest possible OmniVoice within current constraints,” and it is the route most consistent with the upstream compatibility data and CPU tuning guidance reviewed above. citeturn43view0turn6view1turn11view2turn32view0turn31search0
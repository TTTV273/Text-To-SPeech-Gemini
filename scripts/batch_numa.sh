#!/bin/bash
# Batch audiobook TTS across 2 NUMA nodes in parallel.
#
# Distributes .md files across both sockets, each pinned with numactl.
# Uses 8 threads + 8 threads = 16 physical cores total, avoiding
# cross-socket QPI traffic.
#
# Usage:
#   scripts/batch_numa.sh <dir>           # all .md files in <dir>
#   scripts/batch_numa.sh f1.md f2.md ... # explicit file list
#   scripts/batch_numa.sh <dir> --openvino  # use OpenVINO backend
#
# Options:
#   --openvino    Use ov-openvino-numa instead of ov-numa (PyTorch)
#   --workers N   Not used; this script always runs 2 parallel processes
#   --resume      Pass --resume to each TTS process

set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKEND="ov"
RESUME=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --openvino)
            BACKEND="ov-openvino"
            shift
            ;;
        --resume)
            RESUME="--resume"
            shift
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done
set -- "${EXTRA_ARGS[@]}" 2>/dev/null || true

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 [--openvino] [--resume] <dir|file1.md file2.md ...>" >&2
    echo "" >&2
    echo "Examples:" >&2
    echo "  $0 2.DATA/BOOK-2_Learn-Python" >&2
    echo "  $0 --resume 2.DATA/BOOK-2_Learn-Python" >&2
    echo "  $0 --openvino 2.DATA/BOOK-2_Learn-Python" >&2
    exit 1
fi

NUMA_CMD="${BACKEND}-numa"
if ! command -v "$NUMA_CMD" >/dev/null 2>&1; then
    echo "Error: $NUMA_CMD not found in PATH." >&2
    echo "Run: ln -s $REPO_DIR/scripts/*_numa.sh ~/.local/bin/ or use full paths." >&2
    exit 1
fi

if ! command -v numactl >/dev/null 2>&1; then
    echo "Error: numactl is not installed. Install with: sudo pacman -S numactl" >&2
    exit 1
fi

# Collect .md files
FILES=()
for ARG in "$@"; do
    if [ -d "$ARG" ]; then
        while IFS= read -r f; do
            FILES+=("$f")
        done < <(find "$ARG" -maxdepth 1 -name "*.md" | sort)
    elif [ -f "$ARG" ]; then
        FILES+=("$ARG")
    else
        echo "Warning: '$ARG' is not a file or directory, skipping." >&2
    fi
done

TOTAL=${#FILES[@]}
if [ "$TOTAL" -eq 0 ]; then
    echo "Error: No .md files found." >&2
    exit 1
fi

# Split files into 2 groups: even index -> node 0, odd index -> node 1
NODE0_FILES=()
NODE1_FILES=()
for i in "${!FILES[@]}"; do
    if (( i % 2 == 0 )); then
        NODE0_FILES+=("${FILES[$i]}")
    else
        NODE1_FILES+=("${FILES[$i]}")
    fi
done

echo "======================================================="
echo "Batch NUMA TTS"
echo "  Backend:  $BACKEND"
echo "  Total:    $TOTAL files"
echo "  Node 0:   ${#NODE0_FILES[@]} files"
echo "  Node 1:   ${#NODE1_FILES[@]} files"
echo "======================================================="

process_node() {
    local node="$1"
    shift
    local files=("$@")
    local failed=0

    for f in "${files[@]}"; do
        echo "[Node $node] Processing: $f"
        if "$NUMA_CMD" "$node" "$f" --resume $RESUME; then
            echo "[Node $node] Done: $f"
        else
            echo "[Node $node] FAILED: $f"
            ((failed++))
        fi
    done

    return $failed
}

# Run both nodes in parallel
process_node 0 "${NODE0_FILES[@]}" &
PID0=$!

process_node 1 "${NODE1_FILES[@]}" &
PID1=$!

# Wait for both
FAIL0=0
FAIL1=0
wait "$PID0" || FAIL0=1
wait "$PID1" || FAIL1=1

echo "======================================================="
if [ "$FAIL0" -eq 0 ] && [ "$FAIL1" -eq 0 ]; then
    echo "All $TOTAL files completed successfully."
else
    echo "Some files failed. Check output above."
fi
echo "======================================================="

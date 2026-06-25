#!/bin/bash
# Run OmniVoice OpenVINO pinned to one NUMA node.
# Usage: scripts/ov_openvino_numa.sh <node> [voice] <file> [options]

set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <node> [voice] <file> [options]" >&2
    echo "Example: $0 0 chapter.md" >&2
    echo "Example: $0 1 Kore chapter.md --resume" >&2
    exit 1
fi

NODE="$1"
shift

if ! [[ "$NODE" =~ ^[0-9]+$ ]]; then
    echo "Error: NUMA node must be a non-negative integer." >&2
    exit 1
fi

if ! command -v numactl >/dev/null 2>&1; then
    echo "Error: numactl is not installed." >&2
    echo "On Arch Linux, install it with: sudo pacman -S numactl" >&2
    exit 1
fi

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-8}"
export OMP_PROC_BIND="${OMP_PROC_BIND:-close}"
export OMP_PLACES="${OMP_PLACES:-cores}"

exec numactl --cpunodebind="$NODE" --membind="$NODE" \
    "$REPO_DIR/ov-openvino" --torch-threads "$OMP_NUM_THREADS" "$@"

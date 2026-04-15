#!/usr/bin/env bash
# run_contention_profile.sh <main_cu_path> <XSIZE> <YSIZE> <BLOCKX> <BLOCKY> [device_id]

set -eo pipefail

MAIN_CU="${1:?Usage: $0 <main.cu path> <XSIZE> <YSIZE> <BLOCKX> <BLOCKY> [device_id]}"
XSIZE="${2:?Missing XSIZE}"
YSIZE="${3:?Missing YSIZE}"
BLOCKX="${4:?Missing BLOCKX}"
BLOCKY="${5:?Missing BLOCKY}"
DEVICE_ID="${6:-0}"
ENEMY_BINARY="$HOME/LS-CAT/bin/green_enemy"
ENEMY_WARMUP_SLEEP=3
NCU_REPORT_DIR="ncu_reports"
KERNEL_DIR="$(dirname "$(realpath "$MAIN_CU")")"
BINARY="${KERNEL_DIR}/victim_bin"
log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[FATAL] $*" >&2; exit 1; }
cleanup() {
    log "Cleanup: stopping enemy..."
    if [[ -n "${ENEMY_PID:-}" ]]; then
        kill -TERM "$ENEMY_PID" 2>/dev/null || true
        sleep 2
        kill -KILL "$ENEMY_PID" 2>/dev/null || true
        log "Enemy PID=$ENEMY_PID stopped"
    fi
}
trap cleanup EXIT
[[ -f "$MAIN_CU" ]]      || die "main.cu not found: $MAIN_CU"
[[ -f "$ENEMY_BINARY" ]] || die "Enemy binary not found: $ENEMY_BINARY — run build_enemy.sh first."
command -v nvcc &>/dev/null || die "nvcc not found in PATH"
command -v ncu  &>/dev/null || die "ncu not found in PATH"


KERNEL_NAME="$(python3 - "$MAIN_CU" "$KERNEL_DIR" << 'PYEOF'
import re, sys, os
main_cu = sys.argv[1]
kernel_dir = sys.argv[2]
with open(main_cu, 'r', errors='replace') as f:
    main_src = f.read()
included_cu = re.findall(r'#include\s+"([^"]+\.cu)"', main_src)
for fname in included_cu:
    fpath = os.path.join(kernel_dir, fname)
    if os.path.isfile(fpath):
        with open(fpath, 'r', errors='replace') as f:
            src = f.read()
        m = re.search(r'__global__\s+\w[\w\s*]*\s+([\w]+)\s*\(', src)
        if m:
            print(m.group(1))
            sys.exit(0)
m = re.search(r'__global__\s+\w[\w\s*]*\s+([\w]+)\s*\(', main_src)
if m:
    print(m.group(1))
else:
    print('kernel')
PYEOF
)"

log "Victim-Enemy Contention NCU Profile :"
log "  Kernel name: $KERNEL_NAME"
log "  Kernel dir : $KERNEL_DIR"
log "  Matrix     : ${XSIZE}x${YSIZE}"
log "  Block dim  : ${BLOCKX}x${BLOCKY}"
log "  Device     : $DEVICE_ID"

NCU_REPORT_NAME="${KERNEL_NAME}_${XSIZE}x${YSIZE}_b${BLOCKX}x${BLOCKY}"
OUTPUT_CSV="${KERNEL_NAME}_${XSIZE}x${YSIZE}_b${BLOCKX}x${BLOCKY}.csv"
PATCHED_CU="${KERNEL_DIR}/main_patched.cu"
cp "$MAIN_CU" "$PATCHED_CU"

python3 - "$PATCHED_CU" "$XSIZE" "$YSIZE" "$BLOCKX" "$BLOCKY" "$DEVICE_ID" << 'PYEOF'
import sys, re

path, xs, ys, bx, by, dev = sys.argv[1:]

with open(path, 'r', errors='replace') as f:
    src = f.read()
src = re.sub(r'#include\s*[<"]cuda_profiler_api\.h[">]\s*\n?', '', src)
src = re.sub(r'^\s*cudaProfilerStart\(\)\s*;\s*\n', '', src, flags=re.MULTILINE)
src = re.sub(r'^\s*cudaProfilerStop\(\)\s*;\s*\n',  '', src, flags=re.MULTILINE)
src = src.replace('cudaProfilerStop();',  '')
src = src.replace('cudaProfilerStart();', '')
src = re.sub(r'(loop_counter\s*<\s*)\d+', r'\g<1>1', src)
src = re.sub(
    r'int\s+matrices_\s*\[\d+\]\s*\[\s*2\s*\]\s*=\s*\{[^;]*\};',
    f'int matrices_[1][2] = {{{{{xs},{ys}}}}};',
    src)
src = re.sub(
    r'int\s+blocks_\s*\[\d+\]\s*\[\s*2\s*\]\s*=\s*\{[^;]*\};',
    f'int blocks_[1][2] = {{{{{bx},{by}}}}};',
    src)
src = re.sub(
    r'int matrix_end\s*=\s*\([^;]*\)\s*:[^;]+;',
    'int matrix_end = (argc > 2) ? strtol(argv[2], &p, 10) : 1;',
    src)
src = re.sub(
    r'(for\s*\(\s*int\s+block_idx\s*=\s*0\s*;\s*block_idx\s*<\s*)\d+(\s*;)',
    r'\g<1>1\2',
    src)
src = re.sub(r'cudaSetDevice\(\s*\d+\s*\)', f'cudaSetDevice({dev})', src)
src = re.sub(r'int devIdx\s*=\s*\d+',       f'int devIdx = {dev}',   src)
with open(path, 'w') as f:
    f.write(src)
print(f"[PATCH] matrices_[1][2]={{{xs},{ys}}}, blocks_[1][2]={{{bx},{by}}}, device={dev}")
print("[PATCH] All loop counters reduced to 1, profiler API removed")
PYEOF
log "Compiling patched main.cu..."
nvcc -arch=sm_87 -lcuda -lineinfo \
     -I"$KERNEL_DIR" \
     "$PATCHED_CU" \
     -o "$BINARY" \
     2>&1 | sed 's/^/  [nvcc] /'
log "Compiled → $BINARY"
log "Verifying binary runs standalone"
"$BINARY" && log "Standalone run OK" || die "Binary failed"
log "Launching enemy (infinite mode, green ctx, 2 SMs)..."
"$ENEMY_BINARY" 0 1 &
ENEMY_PID=$!
log "Enemy launched PID=$ENEMY_PID, waiting ${ENEMY_WARMUP_SLEEP}s for warmup..."
sleep "$ENEMY_WARMUP_SLEEP"

if ! kill -0 "$ENEMY_PID" 2>/dev/null; then
    die "Enemy process exited immediately"
fi
log "Enemy running: PID=$ENEMY_PID"
mkdir -p "$NCU_REPORT_DIR"

log "Starting NCU profiling of victim under contention"
log "  NCU report : ${NCU_REPORT_DIR}/${NCU_REPORT_NAME}.ncu-rep"
log "  CSV output : $OUTPUT_CSV"

sudo "$(which ncu)" \
    -f \
    --launch-skip 0 \
    --launch-count 1 \
    --csv \
    --set full \
    --page source \
    --print-source cuda,sass \
    -o "${NCU_REPORT_DIR}/${NCU_REPORT_NAME}" \
    "$BINARY" \
    2>&1 | tee "$OUTPUT_CSV"

log "NCU profiling complete."
log "  Binary report : ${NCU_REPORT_DIR}/${NCU_REPORT_NAME}.ncu-rep"
log "  CSV metrics   : $OUTPUT_CSV"

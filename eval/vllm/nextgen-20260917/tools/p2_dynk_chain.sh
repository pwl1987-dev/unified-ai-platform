#!/usr/bin/env bash
# p2_dynk_chain.sh — P2 dynamic-k 链（K5/K6/TONLY/K8CHECK 4 boot）
set -uo pipefail
NEXTGEN=/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917
SBX=/data/sandbox/nextgen-20260917
PY=/data/tools/vllm29-env/bin/python
RUNLOG=$SBX/p2-dynk-chain-runlog.txt
LOCK=$SBX/p2-dynk-chain.lock
DONE=$SBX/p2-dynk-chain.done
U3=GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae
U4=GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e
log() { echo "[$(date '+%F %T')] $*" | tee -a "$RUNLOG"; }
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then log "已有实例"; exit 0; fi
echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' EXIT
[ -f "$DONE" ] && { log "已完成"; exit 0; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id="$1" | tr -d ' '; }
wait34() { local w=0; while [ "$(gpu_used "$U3")" -gt 100 ] || [ "$(gpu_used "$U4")" -gt 100 ]; do [ "$w" -ge 3600 ] && return 1; sleep 60; w=$((w+60)); done; }
log "=== P2 dynk 链启动 ==="
for KEY in K5 K6 TONLY K8CHECK; do
  wait34 || { log "$KEY 等卡超时，退出"; exit 4; }
  "$PY" "$NEXTGEN/tools/p02_screen.py" --arms "$NEXTGEN/repro/p02-arms/p2-dynk.json" \
    --only "$KEY" --boot-tag B01 >> "$SBX/p2-dynk-$KEY.log" 2>&1 && log "$KEY OK" || log "$KEY FAIL（留证）"
done
touch "$DONE"; log "=== P2 dynk 链完成 ==="

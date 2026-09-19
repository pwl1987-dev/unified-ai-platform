#!/usr/bin/env bash
# p1_screens_chain.sh — 9 向 Screen 第一批自治链（14 boot 顺序跑，断点续跑，每 boot 前重验 3+4 空闲）
# 复用 v2 的选对逻辑简化版：优先 3+4；被占则等（GPU2+{5,6,7} 备选对需要 arms patch，本批只在 3+4 跑，
# 若 3+4 长期被占则退出留交互处理——batch1 依赖 B0 同对可比性）。
set -uo pipefail
NEXTGEN=/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917
SBX=/data/sandbox/nextgen-20260917
PY=/data/tools/vllm29-env/bin/python
RUNLOG=$SBX/p1-scr-chain-runlog.txt
LOCK=$SBX/p1-scr-chain.lock
DONE=$SBX/p1-scr-chain.done
U3=GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae
U4=GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e
DEADLINE=$(( $(date +%s) + 12*3600 ))

log() { echo "[$(date '+%F %T')] $*" | tee -a "$RUNLOG"; }
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then log "已有实例"; exit 0; fi
echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' EXIT
[ -f "$DONE" ] && { log "已完成"; exit 0; }

gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id="$1" | tr -d ' '; }
wait34() {
  local w=0
  while [ "$(gpu_used "$U3")" -gt 100 ] || [ "$(gpu_used "$U4")" -gt 100 ]; do
    [ "$w" -ge 3600 ] && return 1
    sleep 60; w=$((w+60))
  done
  return 0
}

log "=== 9 向 Screen batch1 链启动（14 boot）==="
for KEY in MS8BASE MS2 MS1 NBT1024 NBT3072 NBT4096 NBT1024X128 NBT4096X128 CGFULL8 CGFULL16 ARFI ARNOCA DRAFTTP2 BSSON; do
  if ! wait34; then log "$KEY：3+4 被占超 60 分钟，链退出（断点续跑可重启）"; exit 4; fi
  "$PY" "$NEXTGEN/tools/p02_screen.py" --arms "$NEXTGEN/repro/p02-arms/p1-scr-batch1.json" \
    --only "$KEY" --boot-tag B01 >> "$SBX/p1-scr-chain-$KEY.log" 2>&1 \
    && log "$KEY OK" || log "$KEY FAIL（留证；UNSUPPORTED 候选亦如此记录）"
done
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader > "$SBX/p1-scr-chain-final-gpu.txt"
touch "$DONE"
log "=== batch1 链完成；评估留交互 ==="

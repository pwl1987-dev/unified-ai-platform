#!/usr/bin/env bash
# p0b_p1_chain.sh — Phase 02 自治续跑链（P0B 配对扫描 → B0 三形制基线）
# 等待 GPU3+4 腾空（rpg-bakeoff 退场）后自动推进；全程 UUID gate + 断点续跑 + 每 boot 前重验卡空闲。
# CPU/NUMA 冻结：整链同一 taskset cpuset（含 server 与 client，affinity 继承）。
# 铁律：未知进程零触碰；只轮询显存等空闲，绝不 kill；GPU0/1 与 :8000 零触碰。
set -uo pipefail

NEXTGEN=/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917
SBX=/data/sandbox/nextgen-20260917
PY=/data/tools/vllm29-env/bin/python
RUNLOG=$SBX/p0b-p1-chain-runlog.txt
LOCK=$SBX/p0b-p1-chain.lock
DONE_MARKER=$SBX/p0b-p1-chain.done
U2=GPU-41a1986d-e745-9e40-c520-09490081fd44
U3=GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae
U4=GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e

log() { echo "[$(date '+%F %T')] $*" | tee -a "$RUNLOG"; }

# ---- 单实例锁 ----
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  log "已有实例在跑（pid=$(cat $LOCK)），退出"; exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

if [ -f "$DONE_MARKER" ]; then log "done marker 存在，链已完成"; exit 0; fi

gpu_used_mib() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id="$1" | tr -d ' '; }
wait_free() {  # $@: uuids；$WAIT_MAX_S 全局
  local waited=0
  while :; do
    local allfree=1 u used
    for u in "$@"; do
      used=$(gpu_used_mib "$u")
      [ "${used:-9999}" -le 100 ] || { allfree=0; break; }
    done
    [ "$allfree" = 1 ] && return 0
    [ "$waited" -ge "$WAIT_MAX_S" ] && return 1
    sleep 60; waited=$((waited+60))
  done
}

WAIT_MAX_S=$((24*3600))
log "=== 链启动（等待 GPU3+4 腾空，最长 24h；rpg-bakeoff 零触碰）==="
if ! wait_free "$U3" "$U4"; then log "24h 未腾空，链退出（可重启再等）"; exit 3; fi
log "GPU3+4 已空闲"

# ---- 0) topo/NUMA/CPU 条件留档（两对共享的冻结条件）----
mkdir -p "$SBX/p0b-pairscan"
nvidia-smi topo -m > "$SBX/p0b-pairscan/topo-m.txt" 2>&1
numactl --hardware > "$SBX/p0b-pairscan/numactl-h.txt" 2>&1 || true
taskset -pc $$ > "$SBX/p0b-pairscan/chain-affinity.txt"
cp /proc/self/status "$SBX/p0b-pairscan/chain-status.txt"
log "topo/NUMA/affinity 留档完成"

# ---- 1) busbw 对 3+4 ----
cd "$NEXTGEN/tools"
CUDA_VISIBLE_DEVICES="$U3,$U4" P0B_GPU_UUIDS="$U3,$U4" \
  "$PY" -m torch.distributed.run --nproc_per_node=2 --master_port=29801 \
  p0b_busbw.py --out "$SBX/p0b-pairscan/busbw-pair34.json" >> "$RUNLOG" 2>&1 \
  && log "busbw 3+4 OK" || log "busbw 3+4 FAIL（续跑不影响 bench 半）"

# ---- 2) bench 对 3+4 ----
"$PY" p02_screen.py --arms ../repro/p02-arms/p0b-pairs.json --only PAIR34 --boot-tag B01 \
  >> "$SBX/p0b-p1-chain-pair34.log" 2>&1 && log "PAIR34 bench OK" || log "PAIR34 bench FAIL"

# ---- 3) 对照对 2+4（GPU2 也须空闲；等 90 分钟不等就跳过留交互补）----
log "等 GPU2+4（对照对 2+4）…"
WAIT_MAX_S=$((90*60))
if wait_free "$U2" "$U4"; then
  CUDA_VISIBLE_DEVICES="$U2,$U4" P0B_GPU_UUIDS="$U2,$U4" \
    "$PY" -m torch.distributed.run --nproc_per_node=2 --master_port=29802 \
    p0b_busbw.py --out "$SBX/p0b-pairscan/busbw-pair24.json" >> "$RUNLOG" 2>&1 \
    && log "busbw 2+4 OK" || log "busbw 2+4 FAIL"
  "$PY" p02_screen.py --arms ../repro/p02-arms/p0b-pairs.json --only PAIR24 --boot-tag B01 \
    >> "$SBX/p0b-p1-chain-pair24.log" 2>&1 && log "PAIR24 bench OK" || log "PAIR24 bench FAIL"
else
  log "GPU2 90 分钟未空闲，对照对跳过（留交互会话补）"
  echo "SKIPPED_GPU2_BUSY" > "$SBX/p0b-pairscan/pair24-skipped.txt"
fi

# ---- 4) B0-L32 Qualify 3-boot ----
WAIT_MAX_S=$((6*3600))
for BT in B01 B02 B03; do
  wait_free "$U3" "$U4" || { log "B0L32-$BT 等卡超时，链终止（可重启续）"; exit 4; }
  "$PY" p02_screen.py --arms ../repro/p02-arms/p1-b0-baselines.json --only B0L32 --boot-tag "$BT" \
    >> "$SBX/p0b-p1-chain-b0l32.log" 2>&1 && log "B0L32-$BT OK" || log "B0L32-$BT FAIL（留证续跑）"
done

# ---- 5) B0-X128 / B0-X220 Screen reference ----
wait_free "$U3" "$U4" || { log "B0X128 等卡超时"; exit 5; }
"$PY" p02_screen.py --arms ../repro/p02-arms/p1-b0-baselines.json --only B0X128 --boot-tag B01 \
  >> "$SBX/p0b-p1-chain-b0x128.log" 2>&1 && log "B0X128 OK" || log "B0X128 FAIL"
wait_free "$U3" "$U4" || { log "B0X220 等卡超时"; exit 6; }
"$PY" p02_screen.py --arms ../repro/p02-arms/p1-b0-baselines.json --only B0X220 --boot-tag B01 \
  >> "$SBX/p0b-p1-chain-b0x220.log" 2>&1 && log "B0X220 OK" || log "B0X220 FAIL"

# ---- 6) 收链 ----
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader > "$SBX/p0b-pairscan/final-gpu-state.txt"
touch "$DONE_MARKER"
log "=== 链完成（P0B 双对 + B0 三形制）；判定/评估留交互会话 ==="

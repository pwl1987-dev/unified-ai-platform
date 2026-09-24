#!/usr/bin/env bash
# ph5_tp1_followup.sh — TP1 直连链完成后的接力（GPU6 串行复用）：
#   1) 等 ph5_direct_chain.sh tp1 结束
#   2) 关 TP1@36864/MS4（自有 PGID 核验后 kill）
#   3) boot TP1@36864/MS8 → D565-C8 NS×3（= MS8-C8 debt cell，Phase 02 Debt #8 复访）
#   4) 关 MS8 → boot TP1@131072/MS1（T1L 容量探针）→ 成功=D565-C1 冒烟+容量快照；失败=一次性 CAPACITY_LIMIT 取证（不撞墙第二次）
set -uo pipefail
NG=/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917
PY=/data/tools/vllm29-env/bin/python
SBX=/data/sandbox/nextgen-20260917
U6=GPU-30776c79-cd65-60d6-4b56-69c9b6979449

# 1) 等 tp1 直连链
while pgrep -f "ph5_direct_chain.sh tp1" > /dev/null 2>&1; do sleep 20; done
echo "[followup] tp1 direct chain finished: $(date)"

kill_own () {  # kill_own <tag>  —— 仅杀 manifest 登记且身份核验通过的自身 PGID（铁律 5）
  local tag=$1
  local pidfile="$SBX/log-$tag/server.pid" pgidfile="$SBX/log-$tag/server.pgid"
  [ -f "$pidfile" ] || { echo "[kill_own] no pidfile $tag"; return 1; }
  local pid=$(cat "$pidfile") pgid=$(cat "$pgidfile")
  local cmd=$(ps -o cmd= -p "$pid" 2>/dev/null | head -c 80)
  [[ "$cmd" == *vllm* ]] || { echo "[kill_own] pid $pid cmd 非 vllm（$cmd）——拒绝"; return 1; }
  kill -TERM -"$pgid" && echo "[kill_own] TERM pgid=$pgid ($tag)"
  for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done
  kill -0 "$pid" 2>/dev/null && { kill -KILL -"$pgid"; echo "[kill_own] KILL fallback"; }
  sleep 5
}

# 2) 关 MS4 boot
kill_own ph5-smoke-tp1-36864

# 3) MS8 boot + debt cell
setsid bash "$NG/tools/ph5_boot.sh" ph5-ms8-tp1 19713 1 8 --uuids "$U6" --model-len 36864 --spec 1 \
  > "$SBX/ph5-ms8-tp1.boot.log" 2>&1
if curl -sf --max-time 5 http://127.0.0.1:19713/health > /dev/null; then
  SPID=$(cat "$SBX/log-ph5-ms8-tp1/server.pid"); SPGID=$(cat "$SBX/log-ph5-ms8-tp1/server.pgid")
  "$PY" "$NG/tools/run_arm.py" --api http://127.0.0.1:19713/v1 --port 19713 --tp 1 --ms 8 \
    --gpu-uuids "$U6" --server-pid "$SPID" --server-pgid "$SPGID" \
    --tag ph5-ms8-tp1 --exp-prefix V29-PH5-T1F-TP1MS8 --runs ns:3 \
    --fixture d565 --max-tokens 256 --concurrency 8 2>&1 | tail -3
  kill_own ph5-ms8-tp1
else
  echo "[followup] MS8 boot FAILED（见 $SBX/ph5-ms8-tp1.boot.log）—— debt cell 记 BOOT_FAIL"
fi

# 4) T1L 探针：TP1@131072/MS1
setsid bash "$NG/tools/ph5_boot.sh" ph5-t1l-tp1-131072 19713 1 1 --uuids "$U6" --model-len 131072 --spec 1 \
  > "$SBX/ph5-t1l.boot.log" 2>&1
if curl -sf --max-time 5 http://127.0.0.1:19713/health > /dev/null; then
  echo "[T1L] BOOT_ALIVE — 容量快照："
  grep -iE "kv cache|maximum concurrency|GPU KV cache size" "$SBX/log-ph5-t1l-tp1-131072/server.txt" | tail -5 \
    | tee "$SBX/log-ph5-t1l-tp1-131072/capacity.txt"
  curl -s --max-time 60 http://127.0.0.1:19713/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Reply exactly: OK"}],"max_tokens":16,"temperature":0}' \
    | head -c 200; echo
else
  echo "[T1L] BOOT_FAIL —— TP1@131072 容量不可行，一次性取证（CAPACITY_LIMIT），不撞第二次"
  tail -5 "$SBX/ph5-t1l.boot.log"
fi
echo "[followup] ALL DONE: $(date)"

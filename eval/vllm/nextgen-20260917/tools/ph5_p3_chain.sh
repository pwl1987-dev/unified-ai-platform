#!/usr/bin/env bash
# ph5_p3_chain.sh — P3 Qualify 链：3 finalists（T1/T3/T4）× 3 boots（B01-B03）
# 每臂=完整 cell 套件+verbatim canary+整机能量；顺序执行，臂间 sleep 30 冷却
set -uo pipefail
NG=/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917
PY=/data/tools/vllm29-env/bin/python
SBX=/data/sandbox/nextgen-20260917
for T in T1 T3 T4; do
  for B in B01 B02 B03; do
    echo "=== P3 arm $T $B start $(date) ==="
    rm -f "$SBX/ph5-router-routes-$T.jsonl"
    "$PY" "$NG/tools/ph5_p1_run.py" --topology "$T" --boot-tag "$B" \
      > "$SBX/ph5-P3-$T-$B.log" 2>&1
    echo "=== P3 arm $T $B done rc=$? $(date) ==="
    sleep 30
  done
done
echo "ALL P3 ARMS DONE $(date)"

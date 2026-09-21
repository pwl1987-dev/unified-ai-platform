#!/usr/bin/env bash
# Phase 03 主 GPU 链（P1.b/P1.c）：238K+ 正式认证 → KVARN 0.28 参考臂 → churn A/B
# 惯例：LOCK 活性检查 + DONE 标记；逐段即时落盘；前台分步、断点可续。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
NG="$(dirname "$HERE")"
ST="$NG/raw/staging/PH3-KV"
LOCK=/tmp/ph3-master-gpu.lock
DONE="$ST/master-chain.done"
[ -f "$DONE" ] && { echo "[master] already done"; exit 0; }
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "[master] another instance alive ($(cat "$LOCK"))"; exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

wait_port_free() {
  for i in $(seq 1 120); do
    ss -tln 2>/dev/null | grep -q ":19702 " || return 0
    sleep 10
  done
  echo "[master] port 19702 busy timeout"; return 1
}

echo "[master] seg1: certify-238plus (~3h)"
wait_port_free && python3 "$HERE/ph3_certify_238plus.py" >> "$ST/certify-238plus-chain.log" 2>&1
echo "[master] seg1 rc=$?"

echo "[master] seg2: kvarn-0.28 reference (~30min)"
wait_port_free && python3 "$HERE/ph3_kvarn_ref.py" >> "$ST/kvarn-ref-chain.log" 2>&1
echo "[master] seg2 rc=$?"

echo "[master] seg3: churn A/B (~40min)"
wait_port_free && python3 "$HERE/ph3_churn.py" >> "$NG/raw/staging/PH3-P0B/churn-chain.log" 2>&1
echo "[master] seg3 rc=$?"

touch "$DONE"
echo "[master] all segments complete"

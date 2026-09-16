#!/usr/bin/env bash
set -euo pipefail
S=/data/sandbox/vllm-cu130-qual-20260915/usable-matrix-20260916
PY=/data/tools/vllm28-env/bin/python
mkdir -p "$S"
wait_api() {
  local port=$1 kind=$2 c=${3:-0}
  for i in $(seq 1 480); do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 1 "http://127.0.0.1:${port}/v1/models" || true)
    [ "$code" = 200 ] && { echo "$kind READY sec=$i"; return 0; }
    if [ "$kind" = 027 ]; then docker inspect -f '{{.State.Running}}' vllm027-usable-gpu4 2>/dev/null | grep -q true || return 1
    else p=$(cat /data/sandbox/vllm-cu130-qual-20260915/vllm028-usable-c${c}.pid 2>/dev/null || true); [ -z "$p" ] || kill -0 "$p" 2>/dev/null || return 1; fi
    sleep 1
  done
  return 1
}
run_ladder() {
  local ver=$1 port=$2 c=$3; shift 3; local targets=("$@")
  for tok in "${targets[@]}"; do
    out="$S/vllm${ver}-c${c}-${tok}.json"
    echo "TEST ver=$ver c=$c tok=$tok"
    "$PY" /tmp/long_concurrency_probe.py --api "http://127.0.0.1:${port}" --concurrency "$c" --tokens "$tok" --max-tokens 32 --out "$out" > "$S/vllm${ver}-c${c}-${tok}.stdout" 2>&1 || true
    status=$($PY - <<PY
import json
try:
 d=json.load(open('$out')); print(d.get('status','FAIL'))
except Exception: print('FAIL')
PY
)
    echo "RESULT ver=$ver c=$c tok=$tok status=$status"
    [ "$status" = PASS ] || break
  done
}
for c in 1 2 4 6 8; do
  case "$c" in
    1) ladder=(224000 240000) ;;
    2) ladder=(96000 112000 128000 160000) ;;
    4) ladder=(64000 80000 96000 112000) ;;
    6) ladder=(32000 48000 64000 80000) ;;
    8) ladder=(24000 32000 48000 64000) ;;
  esac
  echo "=== START C$c ==="
  /tmp/start027_generic.sh "$c" >/tmp/start027-c${c}.out 2>&1 & s027=$!
  /tmp/start028_generic.sh "$c" >/tmp/start028-c${c}.out 2>&1 & s028=$!
  wait "$s027" || true; wait "$s028" || true
  if wait_api 19638 027 "$c"; then run_ladder 027 19638 "$c" "${ladder[@]}"; else echo "START_FAIL 027 C$c" | tee "$S/vllm027-c${c}-start-fail.txt"; fi
  if wait_api 19637 028 "$c"; then run_ladder 028 19637 "$c" "${ladder[@]}"; else echo "START_FAIL 028 C$c" | tee "$S/vllm028-c${c}-start-fail.txt"; fi
  docker rm -f vllm027-usable-gpu4 >/dev/null 2>&1 || true
  p=$(cat /data/sandbox/vllm-cu130-qual-20260915/vllm028-usable-c${c}.pid 2>/dev/null || true); [ -z "$p" ] || kill -TERM "$p" 2>/dev/null || true
  sleep 3
  echo "=== END C$c ==="
done

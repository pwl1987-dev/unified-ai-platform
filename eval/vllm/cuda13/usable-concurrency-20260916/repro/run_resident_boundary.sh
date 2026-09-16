#!/usr/bin/env bash
set -euo pipefail
S=/data/sandbox/vllm-cu130-qual-20260915/resident-boundary-20260916
PY=/data/tools/vllm28-env/bin/python
mkdir -p "$S"
wait_api() {
  local port=$1 kind=$2 c=$3
  for i in $(seq 1 480); do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 1 "http://127.0.0.1:${port}/v1/models" || true)
    [ "$code" = 200 ] && return 0
    sleep 1
  done
  return 1
}
run_one() {
  local ver=$1 port=$2 c=$3 tok=$4
  local out="$S/vllm${ver}-c${c}-${tok}.json"
  "$PY" /tmp/long_concurrency_probe.py --api "http://127.0.0.1:${port}" --concurrency "$c" --tokens "$tok" --max-tokens 32 --out "$out" > "$out.stdout" 2>&1 || true
  "$PY" - "$out" <<'PY'
import json,sys
try:
 d=json.load(open(sys.argv[1])); print(d.get('status'), d.get('full_resident_concurrency'), d.get('max_running'), d.get('max_waiting'))
except Exception as e: print('FAIL False 0 0')
PY
}
for c in 2 4 6 8; do
  case "$c" in
    2) ladder=(64000 72000 80000 88000 96000) ;;
    4) ladder=(4096 8192 16384 24576 32768 48000 64000) ;;
    6) ladder=(4096) ;;
    8) ladder=(4096) ;;
  esac
  /tmp/start027_generic.sh "$c" >/tmp/res-start027-c${c}.out 2>&1 & a=$!
  /tmp/start028_generic.sh "$c" >/tmp/res-start028-c${c}.out 2>&1 & b=$!
  wait "$a" || true; wait "$b" || true
  wait_api 19638 027 "$c"; wait_api 19637 028 "$c"
  for ver in 027 028; do
    port=19638; [ "$ver" = 028 ] && port=19637
    for tok in "${ladder[@]}"; do
      echo "TEST $ver C$c $tok"
      line=$(run_one "$ver" "$port" "$c" "$tok"); echo "$line"
      full=$(echo "$line" | awk '{print $2}')
      [ "$full" = True ] || break
    done
  done
  docker rm -f vllm027-usable-gpu4 >/dev/null 2>&1 || true
  p=$(cat /data/sandbox/vllm-cu130-qual-20260915/vllm028-usable-c${c}.pid 2>/dev/null || true)
  [ -z "$p" ] || kill -TERM "$p" 2>/dev/null || true
  sleep 3
done

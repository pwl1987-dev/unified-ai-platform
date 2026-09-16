#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASE=${BASE:-/data/sandbox/vllm-cu130-qual-20260915}
OUT_DIR=${OUT_DIR:-$BASE/usable-matrix-repro}
PY=${PY:-/data/tools/vllm28-env/bin/python}
N027=vllm027-usable-gpu4
mkdir -p "$OUT_DIR"
exec > >(tee "$OUT_DIR/runner.log") 2>&1
port_busy() { ss -ltn | grep -Eq ":$1 "; }
wait027() {
  local c=$1 running envc code
  for i in $(seq 1 480); do
    running=$(docker inspect -f '{{.State.Running}}' "$N027" 2>/dev/null || echo false)
    envc=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$N027" 2>/dev/null | sed -n 's/^MAX_SEQS=//p' | tail -1)
    if [ "$running" = true ] && [ "$envc" = "$c" ]; then
      code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:19638/v1/models || true)
      [ "$code" = 200 ] && { echo "027 C$c READY sec=$i"; return 0; }
    fi
    sleep 1
  done
  return 1
}
wait028() {
  local c=$1 p cmd code
  for i in $(seq 1 480); do
    p=$(cat "$BASE/vllm028-usable-c${c}.pid" 2>/dev/null || true)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null || true)
      if grep -Fq -- "--max-num-seqs $c" <<<"$cmd"; then
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:19637/v1/models || true)
        [ "$code" = 200 ] && { echo "028 C$c READY pid=$p sec=$i"; return 0; }
      fi
    fi
    sleep 1
  done
  return 1
}
run_ladder() {
  local ver=$1 port=$2 c=$3; shift 3
  local tok out status
  for tok in "$@"; do
    out="$OUT_DIR/vllm${ver}-c${c}-${tok}.json"
    echo "TEST $ver C$c $tok"
    "$PY" "$HERE/long_concurrency_probe.py" --api "http://127.0.0.1:${port}" --concurrency "$c" --tokens "$tok" --max-tokens 32 --out "$out" > "$out.stdout" 2>&1 || true
    status=$($PY -c "import json; print(json.load(open('$out')).get('status','FAIL'))" 2>/dev/null || echo FAIL)
    echo "RESULT $ver C$c $tok status=$status"
    [ "$status" = PASS ] || break
  done
}
stop_pair() {
  local c=$1 p
  docker rm -f "$N027" >/dev/null 2>&1 || true
  p=$(cat "$BASE/vllm028-usable-c${c}.pid" 2>/dev/null || true)
  [ -z "$p" ] || kill -TERM "$p" 2>/dev/null || true
  for _ in $(seq 1 30); do
    port_busy 19637 || port_busy 19638 || return 0
    sleep 1
  done
  return 1
}
for c in 1 2 4 6 8; do
  case "$c" in
    1) ladder=(224000 240000) ;;
    2) ladder=(96000 112000 128000 160000) ;;
    4) ladder=(64000 80000 96000 112000) ;;
    6) ladder=(32000 48000 64000 80000) ;;
    8) ladder=(24000 32000 48000 64000) ;;
  esac
  stop_pair "$c" || true
  { port_busy 19637 || port_busy 19638; } && { echo "test port occupied before C$c"; exit 2; } || true
  "$HERE/start027-captured.sh" "$c" >"$OUT_DIR/start027-c${c}.out" 2>&1
  "$HERE/start028-captured.sh" "$c" >"$OUT_DIR/start028-c${c}.out" 2>&1
  wait027 "$c" || { docker logs "$N027" --tail 120 || true; exit 3; }
  wait028 "$c" || { tail -120 "$BASE/vllm028-usable-c${c}.log" || true; exit 4; }
  run_ladder 027 19638 "$c" "${ladder[@]}"
  run_ladder 028 19637 "$c" "${ladder[@]}"
  stop_pair "$c"
done
echo USABLE_MATRIX_DONE

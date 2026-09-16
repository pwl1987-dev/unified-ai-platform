#!/usr/bin/env bash
set -euo pipefail
B=/data/sandbox/vllm-cu130-qual-20260915
OUT=$B/strict-c2-028-low-v4-20260916; PY=/data/tools/vllm28-env/bin/python
mkdir -p "$OUT"
wait_ready(){ local tag=$1; for _ in $(seq 1 300); do p=$(cat "$B/vllm028-profile-${tag}.pid" 2>/dev/null||true); [ -n "$p" ] && kill -0 "$p" 2>/dev/null || return 1; code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:19637/v1/models 2>/dev/null||true); [ "$code" = 200 ] && return 0; sleep 2; done; return 1; }
stop(){ local tag=$1 p q; p=$(cat "$B/vllm028-profile-${tag}.pid" 2>/dev/null||true); [ -z "$p" ] || { pkill -TERM -P "$p" 2>/dev/null||true; kill -TERM "$p" 2>/dev/null||true; }; sleep 4; while read -r q; do [ -z "$q" ] || { pkill -KILL -P "$q" 2>/dev/null||true; kill -KILL "$q" 2>/dev/null||true; }; done < <(ps -eo pid,args | awk '/python.*vllm.*--port 19637/ && !/awk/ {print $1}'); }
for spec in '32000 32768' '40000 40960' '44000 45056' '48000 49152'; do
 set -- $spec; tok=$1; maxlen=$2; tag=strictlow-c2-${tok}; echo "START 028 $tag"
 /tmp/start028_profile.sh 2 "$maxlen" 4600000000 "$tag"
 if ! wait_ready "$tag"; then echo "START_FAIL $tag" | tee "$OUT/$tag.start-fail"; stop "$tag"; break; fi
 out="$OUT/$tag.json"; "$PY" /tmp/long_concurrency_probe_v4.py --api http://127.0.0.1:19637 --concurrency 2 --tokens "$tok" --max-tokens 32 --out "$out" >"$out.stdout" 2>&1 || true
 line=$("$PY" - "$out" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); strict=(d['status']=='PASS' and d['max_running']>=2 and d['max_waiting_capacity']==0 and d['preemptions_delta']==0 and d['server_alive_after']); print(d['status'],strict,d['max_running'],d['max_waiting_capacity'],d['max_kv_usage'],d['wall_s'])
PY
 ); echo "RESULT $tag $line"; strict=$(echo "$line"|awk '{print $2}'); stop "$tag"; [ "$strict" = True ] || break
done
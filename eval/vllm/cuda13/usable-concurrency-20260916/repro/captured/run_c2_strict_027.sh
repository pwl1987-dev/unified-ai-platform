#!/usr/bin/env bash
set -euo pipefail
B=/data/sandbox/vllm-cu130-qual-20260915; OUT=$B/strict-c2-027-v4-20260916; PY=/data/tools/vllm28-env/bin/python
mkdir -p "$OUT"
wait_ready(){ local maxlen=$1; for i in $(seq 1 240); do r=$(docker inspect -f '{{.State.Running}}' vllm027-profile-gpu4 2>/dev/null || true); [ "$r" = true ] || return 1; code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:19638/v1/models 2>/dev/null || true); [ "$code" = 200 ] && return 0; sleep 2; done; return 1; }
stop(){ docker rm -f vllm027-profile-gpu4 >/dev/null 2>&1 || true; sleep 2; }
for spec in '48000 49152' '56000 57344' '60000 61440' '62000 63488' '64000 65536'; do
 set -- $spec; tok=$1; maxlen=$2; tag=strict-c2-${tok}; echo "START 027 $tag"
 /tmp/start027_profile.sh 2 "$maxlen" 4600000000 "$tag"
 if ! wait_ready "$maxlen"; then echo "START_FAIL $tag" | tee "$OUT/$tag.start-fail"; stop; break; fi
 out="$OUT/$tag.json"; "$PY" /tmp/long_concurrency_probe_v4.py --api http://127.0.0.1:19638 --concurrency 2 --tokens "$tok" --max-tokens 32 --out "$out" >"$out.stdout" 2>&1 || true
 line=$("$PY" - "$out" <<'PY'
import json,sys
try:
 d=json.load(open(sys.argv[1])); strict=(d.get('status')=='PASS' and d.get('max_running',0)>=2 and d.get('max_waiting_capacity',0)==0 and d.get('preemptions_delta')==0); print(d.get('status'),strict,d.get('max_running'),d.get('max_waiting_capacity'),d.get('max_kv_usage'))
except Exception: print('NOJSON False 0 99 0')
PY
 )
 echo "RESULT $tag $line"; strict=$(echo "$line"|awk '{print $2}'); stop; [ "$strict" = True ] || break
done

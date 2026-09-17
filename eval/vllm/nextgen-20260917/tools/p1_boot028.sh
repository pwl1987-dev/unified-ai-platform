#!/usr/bin/env bash
# P1 KV 因果 A/B 参数化启动器（0.28 认证栈 + overlay-kvarn，四臂同形制）
# 母本: boot028_nextgen.sh；差异：--kv-dtype/--model-len/--kv-mem/--spec 参数化。
# 单变量纪律：四臂 overlay/PYTHONPATH/env/缓存规则完全一致，仅变 kv_cache_dtype
# 及其 derived kv_cache_memory（保相同实际 token capacity）与 speculative 开关。
# 防自杀：runner 须 `setsid bash p1_boot028.sh ...` 调用。
#
# 用法: p1_boot028.sh <tag> <port> <tp> <ms> [选项]
# 选项: --kv-dtype D (kvarn_k4v2_g128|bfloat16|fp8)  --model-len N (默认 225280)
#       --kv-mem BYTES (默认 4820000000)  --spec 0|1 (默认 1)  --cold
set -euo pipefail
TAG=${1:?tag}; PORT=${2:?port}; TP=${3:?tp}; MS=${4:?ms}; shift 4
KV_DTYPE=kvarn_k4v2_g128 MODEL_LEN=225280 KV_MEM=4820000000 SPEC=1 COLD=0
while [[ $# -gt 0 ]]; do case "$1" in
  --kv-dtype) KV_DTYPE=$2; shift 2;;
  --model-len) MODEL_LEN=$2; shift 2;;
  --kv-mem) KV_MEM=$2; shift 2;;
  --spec) SPEC=$2; shift 2;;
  --cold) COLD=1; shift;;
  *) echo "unknown arg $1"; exit 2;;
esac; done

HERE="$(cd "$(dirname "$0")" && pwd)"
SBX=/data/sandbox/nextgen-20260917
VENV=/data/tools/vllm28-env
CUDA13=$VENV/lib/python3.12/site-packages/nvidia/cu13
OVERLAY=/data/sandbox/vllm-cu130-qual-20260915/overlay-kvarn
TARGET=/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128
DRAFT=/data/sandbox/vllm-cu130-qual-20260915/draft-recal-readable-20260915

declare -A ROLE_UUIDS=( [1]="GPU-41a1986d-e745-9e40-c520-09490081fd44"
                        [2]="GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e" )
WANT=${ROLE_UUIDS[$TP]:?unknown tp}
GOT=$("$HERE/nvml_bind.py" snapshot | "$VENV/bin/python" -c "
import json,sys
cards=json.load(sys.stdin)
want='$WANT'.split(',')
got={c['uuid']: c['pci_bdf'] for c in cards}
missing=[u for u in want if u not in got]
print(json.dumps({'ok': not missing, 'missing': missing,
                  'bdf': {u: got.get(u) for u in want}}))")
echo "[gpu-gate] $GOT" | tee "$SBX/$TAG.gpu-gate.txt"
echo "$GOT" | grep -q '"ok": true' || { echo "GPU IDENTITY GATE FAILED — ENV_DRIFT, 阻断"; exit 10; }

export CUDA_VISIBLE_DEVICES="$WANT"
export CUDA_HOME=$CUDA13 PATH="$CUDA13/bin:$VENV/bin:$PATH" PYTHONPATH="$OVERLAY"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_DFLASH2_TORCH_TOPK=1 KVARN_POOL_MEM_FRAC=0.15 VLLM_V2_CUDAGRAPH_MEM_MIB=1000
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$SBX/cache-anchors-tp2}"

if [[ $COLD == 1 ]]; then rm -rf "$VLLM_CACHE_ROOT"; echo "[cache] COLD: removed $VLLM_CACHE_ROOT"; fi
mkdir -p "$VLLM_CACHE_ROOT" "$SBX/log-$TAG"

CMD=("$VENV/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET"
  --served-model-name qwen3.8-27b --host 127.0.0.1 --port "$PORT"
  --tensor-parallel-size "$TP"
  --max-model-len "$MODEL_LEN" --gpu-memory-utilization 0.95 --max-num-seqs "$MS" --max-num-batched-tokens 2048
  --mamba-ssm-cache-dtype float16 --mamba-cache-mode align --prefix-match-unit 128 --async-scheduling
  --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype "$KV_DTYPE"
  --block-size 128)
# KV_MEM=auto => 省略 --kv-cache-memory，由 gpu_memory_utilization 0.95 自动取满
# （bf16/fp8 臂的 derived parameter：容量阶梯判定语义）
[[ -n "$KV_MEM" && "$KV_MEM" != "auto" ]] && CMD+=(--kv-cache-memory "$KV_MEM")
if [[ $SPEC == 1 ]]; then
  CMD+=(--speculative-config "{\"method\":\"dflash\",\"model\":\"$DRAFT\",\"num_speculative_tokens\":7}"
        --compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}')
else
  CMD+=(--compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}')
fi

printf '%s\n' "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES" "VLLM_CACHE_ROOT=$VLLM_CACHE_ROOT" \
  "PORT=$PORT TP=$TP MS=$MS KV=$KV_DTYPE LEN=$MODEL_LEN KV_MEM=$KV_MEM SPEC=$SPEC TAG=$TAG" \
  "${CMD[*]}" > "$SBX/log-$TAG/launch-cmd.txt"

echo "[$TAG] booting tp=$TP ms=$MS port=$PORT kv=$KV_DTYPE len=$MODEL_LEN kv_mem=$KV_MEM spec=$SPEC"
nohup "${CMD[@]}" > "$SBX/log-$TAG/server.txt" 2>&1 &
SRVPID=$!
SRVPGID=$(ps -o pgid= -p "$SRVPID" | tr -d ' ')
echo "$SRVPID" > "$SBX/log-$TAG/server.pid"
echo "$SRVPGID" > "$SBX/log-$TAG/server.pgid"
echo "[$TAG] pid=$SRVPID pgid=$SRVPGID log=$SBX/log-$TAG/server.txt"

for i in $(seq 1 360); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/health"; then
    echo "[$TAG] READY after ~$((i*5))s"
    { grep -iE "kv cache|cache_dtype|attention backend|mamba.*cache|GPU KV cache size|maximum concurrency|Available KV cache" "$SBX/log-$TAG/server.txt" | tail -30; } \
      > "$SBX/log-$TAG/resolved-kv.txt" 2>/dev/null || true
    cat "$SBX/log-$TAG/resolved-kv.txt"
    exit 0
  fi
  if ! kill -0 "$SRVPID" 2>/dev/null; then
    echo "[$TAG] SERVER DIED during boot — see server.txt"
    # 容量/OOM 证据抓取（P1.0 预检与 CAPACITY_LIMIT 判据）
    grep -iE "larger than the maximum number of tokens|KV cache|out of memory|OOM|Free memory" \
      "$SBX/log-$TAG/server.txt" | tail -10 || true
    exit 11
  fi
  sleep 5
done
echo "[$TAG] health timeout"; exit 12

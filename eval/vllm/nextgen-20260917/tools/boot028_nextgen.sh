#!/usr/bin/env bash
# nextgen 0.28 冻结配方启动器（Phase 00）
# 母本: eval/vllm/cuda13/usable-concurrency-20260916/repro/start028-captured.sh
#      + eval/vllm/cuda13/dig028-20260916/tools/boot028.sh（TP 参数化 + cache 钉死）
# 增补（v2.1）: 物理卡位 UUID Gate、PID/PGID 登记、launch-cmd 留档、健康等待。
#
# 用法: boot028_nextgen.sh <tag> <port> <tp> <ms>
#   tag  : 实验组标签（cache root 与 log 目录按它派生）
#   tp   : 1 => GPU2(UUID 41a1986d) | 2 => GPU3+4(UUID 5fa853cd,aab40825)
#   ms   : max_num_seqs
# 环境: COLD_CACHE=1  => 先清空本组 cache root（compile-cache 补债用）
set -euo pipefail
TAG=${1:?tag}; PORT=${2:?port}; TP=${3:?tp}; MS=${4:?ms}
HERE="$(cd "$(dirname "$0")" && pwd)"
NEXTGEN="$(dirname "$HERE")"
SBX=/data/sandbox/nextgen-20260917
VENV=/data/tools/vllm28-env
CUDA13=$VENV/lib/python3.12/site-packages/nvidia/cu13
OVERLAY=/data/sandbox/vllm-cu130-qual-20260915/overlay-kvarn
TARGET=/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128
DRAFT=/data/sandbox/vllm-cu130-qual-20260915/draft-recal-readable-20260915

# ---- 物理卡位 Gate（MANIFEST.yaml gpu_identity_gate）----
declare -A ROLE_UUIDS=( [1]="GPU-41a1986d-e745-9e40-c520-09490081fd44"
                        [2]="GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e" )
WANT=${ROLE_UUIDS[$TP]:?unknown tp}
GOT=$("$HERE/nvml_bind.py" snapshot | "$VENV/bin/python" -c "
import json,sys
cards=json.load(sys.stdin)
want='$WANT'.split(',')
want_set=set(want)
got={c['uuid']: c['pci_bdf'] for c in cards}
missing=[u for u in want if u not in got]
extra_flags=[]
# 校验 UUID 在位 + 记录 BDF
print(json.dumps({'ok': not missing, 'missing': missing,
                  'bdf': {u: got.get(u) for u in want}}))")
echo "[gpu-gate] $GOT" | tee "$SBX/$TAG.gpu-gate.txt"
echo "$GOT" | grep -q '"ok": true' || { echo "GPU IDENTITY GATE FAILED — ENV_DRIFT, 阻断"; exit 10; }

export CUDA_VISIBLE_DEVICES="$WANT"   # 以 UUID 分配，不依赖逻辑 index
export CUDA_HOME=$CUDA13 PATH="$CUDA13/bin:$VENV/bin:$PATH" PYTHONPATH="$OVERLAY"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_CACHE_ROOT="$SBX/cache-$TAG"          # 每组独立，显式钉死
export VLLM_DFLASH2_TORCH_TOPK=1 KVARN_POOL_MEM_FRAC=0.15 VLLM_V2_CUDAGRAPH_MEM_MIB=1000

if [[ ${COLD_CACHE:-0} == 1 ]]; then
  rm -rf "$VLLM_CACHE_ROOT"
  echo "[cache] COLD: removed $VLLM_CACHE_ROOT"
fi
mkdir -p "$VLLM_CACHE_ROOT" "$SBX/log-$TAG"

SPECCFG="{\"method\":\"dflash\",\"model\":\"$DRAFT\",\"num_speculative_tokens\":7}"
CMD=("$VENV/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET"
  --served-model-name qwen3.8-27b --host 127.0.0.1 --port "$PORT"
  --tensor-parallel-size "$TP"
  --max-model-len 245760 --gpu-memory-utilization 0.95 --max-num-seqs "$MS" --max-num-batched-tokens 2048
  --mamba-ssm-cache-dtype float16 --mamba-cache-mode align --prefix-match-unit 128 --async-scheduling
  --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype kvarn_k4v2_g128
  --block-size 128 --kv-cache-memory 4820000000
  --speculative-config "$SPECCFG"
  --compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}')

printf '%s\n' "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES" "VLLM_CACHE_ROOT=$VLLM_CACHE_ROOT" \
  "PORT=$PORT TP=$TP MS=$MS TAG=$TAG" "${CMD[*]}" > "$SBX/log-$TAG/launch-cmd.txt"

echo "[$TAG] booting tp=$TP ms=$MS port=$PORT cache=$VLLM_CACHE_ROOT"
nohup "${CMD[@]}" > "$SBX/log-$TAG/server.txt" 2>&1 &
SRVPID=$!
SRVPGID=$(ps -o pgid= -p "$SRVPID" | tr -d ' ')
echo "$SRVPID" > "$SBX/log-$TAG/server.pid"
echo "$SRVPGID" > "$SBX/log-$TAG/server.pgid"
echo "[$TAG] pid=$SRVPID pgid=$SRVPGID log=$SBX/log-$TAG/server.txt"

# 健康等待（最长 1800s：冷编译可能很长）
for i in $(seq 1 360); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/health"; then
    echo "[$TAG] READY after ~$((i*5))s"
    exit 0
  fi
  if ! kill -0 "$SRVPID" 2>/dev/null; then
    echo "[$TAG] SERVER DIED during boot — see server.txt"; exit 11
  fi
  sleep 5
done
echo "[$TAG] health timeout"; exit 12

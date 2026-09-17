#!/usr/bin/env bash
# nextgen 0.29 参数化启动器（Phase 01，计划 v1.2）
# 母本: tools/boot028_nextgen.sh；差异：
#   1. venv=/data/tools/vllm29-env（本战役可写，补丁 in-tree + .orig 备份 + tree-hash 台账）
#   2. --kv-cache-memory → --kv-cache-memory-bytes（0.29 CLI 改名；per-GPU；not-None 时忽略 gpu_memory_utilization）
#   3. 无 PYTHONPATH overlay（补丁直接进 0.29 树）；overlay 专属环境变量在补丁单元缺失时显式告警
#   4. 补丁级验证（--patch a|b|c）：所需符号缺失 => 启动前 FAIL，不打哑谜
#   5. boot 后抓 resolved KV dtype 三元组（attention/Mamba conv/Mamba SSM）落盘
# 防自杀：runner 须以 `setsid bash boot029_nextgen.sh ...` 调用；本脚本 nohup server 并登记 PID/PGID。
#
# 用法: boot029_nextgen.sh <tag> <port> <tp> <ms> [选项]
#   tp: 1 => GPU2(UUID 41a1986d) | 2 => GPU3+4(5fa853cd,aab40825)
# 选项:
#   --kv-dtype D        auto|bfloat16|float16|fp8|...（默认 auto）
#   --model-len N       默认 32768（Layer A）
#   --kv-mem BYTES      per-GPU KV 字节预算（默认不传=按 gpu_memory_utilization 推断）
#   --spec 0|1          DFlash2 recal k=7（默认 0=Layer A）
#   --patch a|b|c       要求的补丁级（默认 a）
#   --cold              清空本组 VLLM_CACHE_ROOT
set -euo pipefail
TAG=${1:?tag}; PORT=${2:?port}; TP=${3:?tp}; MS=${4:?ms}; shift 4
KV_DTYPE=auto MODEL_LEN=32768 KV_MEM="" SPEC=0 PATCH=a COLD=0
while [[ $# -gt 0 ]]; do case "$1" in
  --kv-dtype) KV_DTYPE=$2; shift 2;;
  --model-len) MODEL_LEN=$2; shift 2;;
  --kv-mem) KV_MEM=$2; shift 2;;
  --spec) SPEC=$2; shift 2;;
  --patch) PATCH=$2; shift 2;;
  --cold) COLD=1; shift;;
  *) echo "unknown arg $1"; exit 2;;
esac; done

HERE="$(cd "$(dirname "$0")" && pwd)"
NEXTGEN="$(dirname "$HERE")"
SBX=/data/sandbox/nextgen-20260917
VENV=/data/tools/vllm29-env
SITE=$VENV/lib/python3.12/site-packages
CUDA13=$SITE/nvidia/cu13
TARGET=/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128
DRAFT=/data/sandbox/vllm-cu130-qual-20260915/draft-recal-readable-20260915

# ---- 物理卡位 Gate（与 MANIFEST gpu_identity_gate 一致）----
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

# ---- 补丁级验证（in-tree 符号检查；缺失即 FAIL）----
check_patch() {
  case "$1" in
    a) grep -q "quant_config" <(sed -n '/self.embed_tokens = VocabParallelEmbedding(/,/)/p' "$SITE/vllm/model_executor/models/qwen3_5.py") \
         || { echo "[patch-a] FAIL: qwen3_5.py embed_tokens 未带 quant_config（unit a 未移植）"; exit 20; } ;;
    b) grep -q "_dense_kv_rows" "$SITE/vllm/model_executor/models/qwen3_dflash.py" 2>/dev/null \
         || { echo "[patch-b] FAIL: qwen3_dflash.py 无 _dense_kv_rows（unit b 未移植）"; exit 21; } ;;
    c) [[ -d "$SITE/vllm/model_executor/layers/quantization/kvarn" ]] \
         || { echo "[patch-c] FAIL: kvarn quant 包不存在（unit d 未移植）"; exit 22; } ;;
  esac
}
check_patch "$PATCH"

# ---- overlay 专属环境变量静默失效告警（0.29 无 overlay 时这些变量是死的）----
overlay_env_guard() {
  local dead=()
  [[ -n "${KVARN_POOL_MEM_FRAC:-}" ]] && [[ ! -d "$SITE/vllm/model_executor/layers/quantization/kvarn" ]] && dead+=("KVARN_POOL_MEM_FRAC")
  [[ -n "${VLLM_DFLASH2_TORCH_TOPK:-}" ]] && ! grep -q "VLLM_DFLASH2_TORCH_TOPK" "$SITE/vllm/model_executor/layers/logits_processor.py" && dead+=("VLLM_DFLASH2_TORCH_TOPK")
  [[ -n "${VLLM_V2_CUDAGRAPH_MEM_MIB:-}" ]] && ! grep -q "VLLM_V2_CUDAGRAPH_MEM_MIB" "$SITE/vllm/v1/worker/gpu/model_runner.py" && dead+=("VLLM_V2_CUDAGRAPH_MEM_MIB")
  if [[ ${#dead[@]} -gt 0 ]]; then
    echo "[env-guard] WARNING: 这些环境变量在当前 0.29 树中无消费者（静默失效）: ${dead[*]}" | tee -a "$SBX/$TAG.env-guard.txt"
  fi
}

export CUDA_VISIBLE_DEVICES="$WANT"
export CUDA_HOME=$CUDA13 PATH="$CUDA13/bin:$VENV/bin:$PATH"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$SBX/cache-$TAG}"

if [[ $COLD == 1 ]]; then rm -rf "$VLLM_CACHE_ROOT"; echo "[cache] COLD: removed $VLLM_CACHE_ROOT"; fi
mkdir -p "$VLLM_CACHE_ROOT" "$SBX/log-$TAG"

CMD=("$VENV/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET"
  --served-model-name qwen3.8-27b --host 127.0.0.1 --port "$PORT"
  --tensor-parallel-size "$TP"
  --max-model-len "$MODEL_LEN" --gpu-memory-utilization 0.95 --max-num-seqs "$MS" --max-num-batched-tokens 2048
  --mamba-ssm-cache-dtype float16 --mamba-cache-mode align --prefix-match-unit 128 --async-scheduling
  --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype "$KV_DTYPE"
  --block-size 128
  --compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}')
[[ -n "$KV_MEM" ]] && CMD+=(--kv-cache-memory-bytes "$KV_MEM")
if [[ $SPEC == 1 ]]; then
  CMD+=(--speculative-config "{\"method\":\"dflash\",\"model\":\"$DRAFT\",\"num_speculative_tokens\":7}")
fi

printf '%s\n' "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES" "VLLM_CACHE_ROOT=$VLLM_CACHE_ROOT" \
  "PORT=$PORT TP=$TP MS=$MS KV=$KV_DTYPE LEN=$MODEL_LEN KV_MEM=${KV_MEM:-infer} SPEC=$SPEC PATCH=$PATCH TAG=$TAG" \
  "${CMD[*]}" > "$SBX/log-$TAG/launch-cmd.txt"

echo "[$TAG] booting tp=$TP ms=$MS port=$PORT kv=$KV_DTYPE len=$MODEL_LEN spec=$SPEC patch=$PATCH cache=$VLLM_CACHE_ROOT"
nohup "${CMD[@]}" > "$SBX/log-$TAG/server.txt" 2>&1 &
SRVPID=$!
SRVPGID=$(ps -o pgid= -p "$SRVPID" | tr -d ' ')
echo "$SRVPID" > "$SBX/log-$TAG/server.pid"
echo "$SRVPGID" > "$SBX/log-$TAG/server.pgid"
echo "[$TAG] pid=$SRVPID pgid=$SRVPGID log=$SBX/log-$TAG/server.txt"

# ---- 健康等待（冷编译最长 1800s）----
for i in $(seq 1 360); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/health"; then
    echo "[$TAG] READY after ~$((i*5))s"
    # resolved KV dtype 三元组 + 容量抓取（容量预检 P1.0 证据）
    { grep -iE "kv cache|cache_dtype|kv_cache_dtype|attention backend|mamba.*cache|GPU KV cache size|maximum concurrency" "$SBX/log-$TAG/server.txt" | tail -30; } \
      > "$SBX/log-$TAG/resolved-kv.txt" 2>/dev/null || true
    cat "$SBX/log-$TAG/resolved-kv.txt"
    exit 0
  fi
  if ! kill -0 "$SRVPID" 2>/dev/null; then
    echo "[$TAG] SERVER DIED during boot — see server.txt"; exit 11
  fi
  sleep 5
done
echo "[$TAG] health timeout"; exit 12

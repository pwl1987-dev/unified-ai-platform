#!/usr/bin/env bash
# ph5_boot.sh — Phase 05 拓扑赛 backend 启动器（gates-phase05.yaml launcher 条款）
# 母本: tools/boot029_nextgen.sh（Phase 01-04 认证启动器）；差异仅三处，其余逐字继承：
#   1. 显式 --uuids U1[,U2,...]（数量须=TP；替代固定 ROLE_UUIDS 表——T1/T3 多实例同 TP 并存）
#   2. TP4 合法（数量=4 即可；nvml_bind 全在册校验）
#   3. AUTHORIZED_UUIDS = Phase 05 授权卡集（MANIFEST phase05.gpu_authorization；
#      2026-09-25 实况 = GPU3/GPU4/GPU6；GPU0/1=生产、GPU2=rpg-bakeoff 外占、GPU5/7=外围 vLLM）
# serve 参数/env/补丁校验/健康等待/launch-cmd 落盘与母本一致（含 --kv-dtype bfloat16 显式 NATIVE_BF16）
# 防自杀：runner 须以 `setsid bash ph5_boot.sh ...` 调用；本脚本 nohup server 并登记 PID/PGID。
#
# 用法: ph5_boot.sh <tag> <port> <tp> <ms> --uuids U1[,U2,...] [选项]
# 选项（与母本同名同义）:
#   --model-len N (默认 36864=TP1 认证形制) / --kv-mem BYTES / --spec 0|1 (默认 1=Phase05 全臂 spec k7)
#   --k N / --draft-tp N / --cg-cap N / --nbt N / --cold / --patch a|b|c (默认 a)
#   --target PATH (默认 Q0 anchor)
set -euo pipefail
TAG=${1:?tag}; PORT=${2:?port}; TP=${3:?tp}; MS=${4:?ms}; shift 4
MODEL_LEN=36864 KV_MEM="" SPEC=1 PATCH=a COLD=0
NBT=2048 CG_CAP=8 DRAFT_TP=0 SPEC_K=7 UUIDS=""
TARGET_OVERRIDE=""
while [[ $# -gt 0 ]]; do case "$1" in
  --uuids) UUIDS=$2; shift 2;;
  --model-len) MODEL_LEN=$2; shift 2;;
  --kv-mem) KV_MEM=$2; shift 2;;
  --spec) SPEC=$2; shift 2;;
  --patch) PATCH=$2; shift 2;;
  --cold) COLD=1; shift;;
  --nbt) NBT=$2; shift 2;;
  --cg-cap) CG_CAP=$2; shift 2;;
  --draft-tp) DRAFT_TP=$2; shift 2;;
  --k) SPEC_K=$2; shift 2;;
  --target) TARGET_OVERRIDE=$2; shift 2;;
  *) echo "unknown arg $1"; exit 2;;
esac; done
[[ -n "$UUIDS" ]] || { echo "Phase05 必须显式 --uuids（授权卡集见 MANIFEST phase05）"; exit 3; }

HERE="$(cd "$(dirname "$0")" && pwd)"
SBX=/data/sandbox/nextgen-20260917
VENV=/data/tools/vllm29-env
SITE=$VENV/lib/python3.12/site-packages
CUDA13=$SITE/nvidia/cu13
TARGET=/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128
[[ -n "$TARGET_OVERRIDE" ]] && TARGET=$TARGET_OVERRIDE
DRAFT=/data/sandbox/vllm-cu130-qual-20260915/draft-recal-readable-20260915

# ---- Phase05 授权卡集 Gate（2026-09-25 巡检实况；GPU0/1 生产、GPU2 rpg-bakeoff、GPU5/7 外围 —— 零触碰）----
AUTHORIZED_UUIDS="GPU-41a1986d-e745-9e40-c520-09490081fd44 GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e GPU-30776c79-cd65-60d6-4b56-69c9b6979449"
IFS=',' read -ra _U <<< "$UUIDS"
[[ ${#_U[@]} -eq $TP ]] || { echo "--uuids 数量须等于 tp=$TP"; exit 9; }
for u in "${_U[@]}"; do
  [[ " $AUTHORIZED_UUIDS " == *" $u "* ]] || { echo "[ph5-gate] $u 不在 Phase05 授权集（GPU3/4/6）— 拒绝"; exit 9; }
done
GOT=$("$HERE/nvml_bind.py" snapshot | "$VENV/bin/python" -c "
import json,sys
cards=json.load(sys.stdin)
want='$UUIDS'.split(',')
got={c['uuid']: c['pci_bdf'] for c in cards}
missing=[u for u in want if u not in got]
print(json.dumps({'ok': not missing, 'missing': missing, 'bdf': {u: got.get(u) for u in want}}))")
echo "[ph5-gpu-gate] $GOT" | tee "$SBX/$TAG.gpu-gate.txt"
echo "$GOT" | grep -q '"ok": true' || { echo "GPU IDENTITY GATE FAILED — ENV_DRIFT, 阻断"; exit 10; }

# ---- 补丁级验证（与母本一致）----
check_patch() {
  case "$1" in
    a) grep -q "quant_config" <(sed -n '/self.embed_tokens = VocabParallelEmbedding(/,/)/p' "$SITE/vllm/model_executor/models/qwen3_5.py") \
         || { echo "[patch-a] FAIL: qwen3_5.py embed_tokens 未带 quant_config"; exit 20; } ;;
    b) grep -q "_dense_kv_rows" "$SITE/vllm/model_executor/models/qwen3_dflash.py" 2>/dev/null \
         || { echo "[patch-b] FAIL"; exit 21; } ;;
    c) [[ -d "$SITE/vllm/model_executor/layers/quantization/kvarn" ]] \
         || { echo "[patch-c] FAIL"; exit 22; } ;;
  esac
}
check_patch "$PATCH"

export CUDA_VISIBLE_DEVICES="$UUIDS"
export CUDA_HOME=$CUDA13 PATH="$CUDA13/bin:$VENV/bin:$PATH"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_DFLASH2_TORCH_TOPK=1
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$SBX/cache-$TAG}"

if [[ $COLD == 1 ]]; then rm -rf "$VLLM_CACHE_ROOT"; echo "[cache] COLD: removed $VLLM_CACHE_ROOT"; fi
mkdir -p "$VLLM_CACHE_ROOT" "$SBX/log-$TAG"

CMD=("$VENV/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET"
  --served-model-name qwen3.8-27b --host 127.0.0.1 --port "$PORT"
  --tensor-parallel-size "$TP"
  --max-model-len "$MODEL_LEN" --gpu-memory-utilization 0.95 --max-num-seqs "$MS" --max-num-batched-tokens "$NBT"
  --mamba-ssm-cache-dtype float16 --mamba-cache-mode align --async-scheduling
  --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype bfloat16
  --block-size 128
  --compilation-config "{\"max_cudagraph_capture_size\":$CG_CAP,\"custom_ops\":[\"+rms_norm\",\"+silu_and_mul\"]}")
[[ -n "$KV_MEM" && "$KV_MEM" != "auto" ]] && CMD+=(--kv-cache-memory-bytes "$KV_MEM")
read -ra _EXTRA <<< "${EXTRA_SERVE_ARGS:-}"
CMD+=("${_EXTRA[@]}")
if [[ $SPEC == 1 ]]; then
  SPECJSON="{\"method\":\"dflash\",\"model\":\"$DRAFT\",\"num_speculative_tokens\":$SPEC_K"
  [[ $DRAFT_TP -ge 1 ]] && SPECJSON+=",\"draft_tensor_parallel_size\":$DRAFT_TP"
  SPECJSON+="}"
  CMD+=(--speculative-config "$SPECJSON")
fi

printf '%s\n' "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES" "VLLM_CACHE_ROOT=$VLLM_CACHE_ROOT" \
  "PORT=$PORT TP=$TP MS=$MS KV=bfloat16 LEN=$MODEL_LEN KV_MEM=${KV_MEM:-infer} SPEC=$SPEC PATCH=$PATCH TAG=$TAG" \
  "${CMD[*]}" > "$SBX/log-$TAG/launch-cmd.txt"

echo "[$TAG] booting tp=$TP ms=$MS port=$PORT kv=bfloat16 len=$MODEL_LEN spec=$SPEC uuids=$UUIDS"
nohup "${CMD[@]}" > "$SBX/log-$TAG/server.txt" 2>&1 &
SRVPID=$!
SRVPGID=$(ps -o pgid= -p "$SRVPID" | tr -d ' ')
echo "$SRVPID" > "$SBX/log-$TAG/server.pid"
echo "$SRVPGID" > "$SBX/log-$TAG/server.pgid"
echo "$UUIDS" > "$SBX/log-$TAG/server.uuids"
echo "[$TAG] pid=$SRVPID pgid=$SRVPGID log=$SBX/log-$TAG/server.txt"

for i in $(seq 1 360); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/health"; then
    echo "[$TAG] READY after ~$((i*5))s"
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

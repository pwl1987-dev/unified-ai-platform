#!/usr/bin/env bash
# 0.28 深挖 boot 器 — 配方冻结自 eval/vllm/cuda13/usable-concurrency-20260916/repro/start_vllm028.sh
# 用法: boot028.sh <tag> <max_len> <port> <k> [method] [extra_spec_json]
set -euo pipefail
TAG=${1:?tag}; MAXLEN=${2:-32768}; PORT=${3:-19640}; K=${4:-7}; METHOD=${5:-dflash}; EXTRA=${6:-}
VENV=/data/tools/vllm28-env; GPU=2
TARGET_DIR=/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128
DRAFT_DIR=/data/sandbox/vllm-cu130-qual-20260915/draft-recal-readable-20260915
CUDA13=$VENV/lib/python3.12/site-packages/nvidia/cu13
OVERLAY=/data/sandbox/vllm-cu130-qual-20260915/overlay-kvarn
export CUDA_VISIBLE_DEVICES=$GPU CUDA_HOME=$CUDA13 PATH="$CUDA13/bin:$VENV/bin:$PATH" PYTHONPATH="$OVERLAY"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-/data/sandbox/dig028-20260916/cache-$TAG}"
export VLLM_DFLASH2_TORCH_TOPK=1 KVARN_POOL_MEM_FRAC=0.15 VLLM_V2_CUDAGRAPH_MEM_MIB=1000
SPECCFG="{\"method\":\"$METHOD\",\"model\":\"$DRAFT_DIR\",\"num_speculative_tokens\":$K${EXTRA:+,$EXTRA}}"
echo "[$TAG] spec=$SPECCFG maxlen=$MAXLEN port=$PORT gpu=$GPU"
exec "$VENV/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET_DIR" \
  --served-model-name qwen3.8-27b --host 127.0.0.1 --port "$PORT" \
  --max-model-len "$MAXLEN" --gpu-memory-utilization 0.95 --max-num-seqs 1 --max-num-batched-tokens 2048 \
  --mamba-ssm-cache-dtype float16 --mamba-cache-mode align --prefix-match-unit 128 --async-scheduling \
  --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype kvarn_k4v2_g128 \
  --block-size 128 --kv-cache-memory 4820000000 \
  --speculative-config "$SPECCFG" \
  --compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}'

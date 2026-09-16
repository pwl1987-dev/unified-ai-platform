#!/usr/bin/env bash
set -euo pipefail
: "${TARGET_DIR:?set TARGET_DIR to exact target checkpoint}"
: "${DRAFT_DIR:?set DRAFT_DIR to exact recal DFlash2 checkpoint}"
GPU=${GPU:-4}; PORT=${PORT:-19638}; MAX_SEQS=${MAX_SEQS:-1}
IMAGE=${IMAGE:-nvidia-4090-llm-inference:0.27.1-cu129}
CACHE_DIR=${CACHE_DIR:-$PWD/.cache-vllm027}; mkdir -p "$CACHE_DIR"
docker rm -f vllm027-repro >/dev/null 2>&1 || true
docker run -d --name vllm027-repro --gpus "device=$GPU" --network host \
  -v "$TARGET_DIR:/app/models/coding-v1.1-W4A16:ro" \
  -v "$DRAFT_DIR:/app/models/Qwen3.8-27B-DFlash2-W4A16-recal:ro" \
  -v "$CACHE_DIR:/cache:rw" \
  -e PORT="$PORT" -e MAX_SEQS="$MAX_SEQS" -e MAX_LEN=245760 -e DFLASH_MAX_LEN=245760 \
  -e MODEL=/app/models/coding-v1.1-W4A16 -e DRAFT=/app/models/Qwen3.8-27B-DFlash2-W4A16-recal \
  -e SPEC=dflash2 -e DFLASH_TOKENS=7 -e CTX=huge -e KV_MEM=4820000000 -e CG=8 \
  -e GPU_UTIL=0.95 -e PREFIX_CACHE=1 -e LOOKUP=0 -e VISION=0 -e VISION_OFFLOAD=0 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True -e VLLM_V2_CUDAGRAPH_MEM_MIB=1000 \
  -e VLLM_NO_USAGE_STATS=1 -e REQ_METRICS=1 \
  -e EXTRA_ARGS="--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3" \
  "$IMAGE" single

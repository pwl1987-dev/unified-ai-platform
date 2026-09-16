#!/usr/bin/env bash
set -euo pipefail
: "${TARGET_DIR:?set TARGET_DIR to exact target checkpoint}"
: "${DRAFT_DIR:?set DRAFT_DIR to exact recal DFlash2 checkpoint}"
VENV=${VENV:-/opt/qwen-vllm028}; GPU=${GPU:-2}; PORT=${PORT:-19637}; MAX_SEQS=${MAX_SEQS:-1}
CUDA13=${CUDA13:-$VENV/lib/python3.12/site-packages/nvidia/cu13}
export CUDA_VISIBLE_DEVICES="$GPU" CUDA_HOME="$CUDA13" PATH="$CUDA13/bin:$VENV/bin:$PATH"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_DFLASH2_TORCH_TOPK=1 KVARN_POOL_MEM_FRAC=0.15 VLLM_V2_CUDAGRAPH_MEM_MIB=1000
exec "$VENV/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET_DIR" \
  --served-model-name qwen3.8-27b --host 127.0.0.1 --port "$PORT" \
  --max-model-len 245760 --gpu-memory-utilization 0.95 --max-num-seqs "$MAX_SEQS" --max-num-batched-tokens 2048 \
  --mamba-ssm-cache-dtype float16 --mamba-cache-mode align --prefix-match-unit 128 --async-scheduling \
  --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype kvarn_k4v2_g128 \
  --block-size 128 --kv-cache-memory 4820000000 \
  --speculative-config "{\"method\":\"dflash\",\"model\":\"$DRAFT_DIR\",\"num_speculative_tokens\":7}" \
  --compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}'

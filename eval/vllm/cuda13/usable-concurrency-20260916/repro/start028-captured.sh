#!/usr/bin/env bash
set -euo pipefail
C=${1:?concurrency}; V=/data/tools/vllm28-env; CUDA13=$V/lib/python3.12/site-packages/nvidia/cu13
O=/data/sandbox/vllm-cu130-qual-20260915/overlay-kvarn; S=/data/sandbox/vllm-cu130-qual-20260915
TARGET=/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128; DRAFT=$S/draft-recal-readable-20260915
LOG=$S/vllm028-usable-c${C}.log; PID=$S/vllm028-usable-c${C}.pid
pkill -TERM -f 'vllm.entrypoints.cli.main serve .*--port 19637' 2>/dev/null || true; sleep 2
: > "$LOG"; export CUDA_VISIBLE_DEVICES=2 CUDA_HOME="$CUDA13" PATH="$CUDA13/bin:$V/bin:$PATH" PYTHONPATH="$O"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_DFLASH2_TORCH_TOPK=1 KVARN_POOL_MEM_FRAC=0.15 VLLM_V2_CUDAGRAPH_MEM_MIB=1000
nohup "$V/bin/python" -m vllm.entrypoints.cli.main serve "$TARGET" --served-model-name qwen3.8-27b --host 127.0.0.1 --port 19637 \
 --max-model-len 245760 --gpu-memory-utilization 0.95 --max-num-seqs "$C" --max-num-batched-tokens 2048 --mamba-ssm-cache-dtype float16 --mamba-cache-mode align \
 --prefix-match-unit 128 --async-scheduling --language-model-only --enable-prefix-caching --generation-config vllm --kv-cache-dtype kvarn_k4v2_g128 --block-size 128 \
 --kv-cache-memory 4820000000 --speculative-config "{\"method\":\"dflash\",\"model\":\"$DRAFT\",\"num_speculative_tokens\":7}" \
 --compilation-config '{"max_cudagraph_capture_size":8,"custom_ops":["+rms_norm","+silu_and_mul"]}' >"$LOG" 2>&1 &
echo $! > "$PID"; echo PID=$(cat "$PID") LOG=$LOG

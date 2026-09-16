#!/usr/bin/env bash
set -euo pipefail
C=${1:?concurrency}
S=/data/sandbox/vllm-cu130-qual-20260915
NAME=vllm027-usable-gpu4
ENVF=$S/vllm027-usable-c${C}.env
CACHE=$(mktemp -d "$S/cache-vllm027-c${C}-XXXXXX")
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker inspect zx-ab-vllm-qwen-1 --format '{{range .Config.Env}}{{println .}}{{end}}' > "$ENVF"
sed -i -E "s/^PORT=.*/PORT=19638/; s/^MAX_SEQS=.*/MAX_SEQS=$C/; s/^VISION=.*/VISION=0/; s/^VISION_OFFLOAD=.*/VISION_OFFLOAD=0/; s/^LOOKUP=.*/LOOKUP=0/; s/^KV_MEM=.*/KV_MEM=4820000000/; s/^CG=.*/CG=8/" "$ENVF"
grep -q '^KV_MEM=' "$ENVF" || echo 'KV_MEM=4820000000' >> "$ENVF"
grep -q '^CG=' "$ENVF" || echo 'CG=8' >> "$ENVF"
grep -q '^PYTORCH_CUDA_ALLOC_CONF=' "$ENVF" && sed -i 's/^PYTORCH_CUDA_ALLOC_CONF=.*/PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True/' "$ENVF" || echo 'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True' >> "$ENVF"
echo 'VLLM_NO_USAGE_STATS=1' >> "$ENVF"
echo "EXPERIMENT_CACHE=$CACHE"
docker run -d --name "$NAME" --gpus '"device=4"' --network host --env-file "$ENVF" \
  -v /data/models:/data/models:ro -v "$CACHE:/cache:rw" \
  -v /data/sandbox/ab-vllm/repo/models:/app/models:rw \
  nvidia-4090-llm-inference:0.27.1-cu129 single

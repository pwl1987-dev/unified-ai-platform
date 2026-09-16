#!/usr/bin/env bash
set -euo pipefail
C=${1:?concurrency}; MAXLEN=${2:?max_model_len}; KVMEM=${3:?kv_bytes}; TAG=${4:?tag}
B=/data/sandbox/vllm-cu130-qual-20260915; NAME=vllm027-profile-gpu4
STAMP=$(date +%Y%m%d-%H%M%S); if [ "$C" = 2 ]; then CACHE="$B/cache-vllm027-profile-c2-shared"; else CACHE="$B/cache-vllm027-profile-${TAG}-${STAMP}"; fi; ENVF="$B/vllm027-profile-${TAG}-${STAMP}.env"
SEED="$B/cache-vllm027-seed"; docker rm -f "$NAME" >/dev/null 2>&1 || true
mkdir -p "$CACHE/.cache"; [ ! -d "$SEED/.cache/flashinfer" ] || cp -a --reflink=auto "$SEED/.cache/flashinfer" "$CACHE/.cache/"
docker inspect zx-ab-vllm-qwen-1 --format '{{range .Config.Env}}{{println .}}{{end}}' > "$ENVF"
sed -i -E "s/^PORT=.*/PORT=19638/; s/^MAX_SEQS=.*/MAX_SEQS=$C/; s/^MAX_LEN=.*/MAX_LEN=$MAXLEN/; s/^DFLASH_MAX_LEN=.*/DFLASH_MAX_LEN=$MAXLEN/; s/^KV_MEM=.*/KV_MEM=$KVMEM/; s/^CG=.*/CG=8/; s/^VISION=.*/VISION=0/; s/^VISION_OFFLOAD=.*/VISION_OFFLOAD=0/; s/^LOOKUP=.*/LOOKUP=0/" "$ENVF"
grep -q '^MAX_LEN=' "$ENVF" || echo "MAX_LEN=$MAXLEN" >> "$ENVF"
grep -q '^DFLASH_MAX_LEN=' "$ENVF" || echo "DFLASH_MAX_LEN=$MAXLEN" >> "$ENVF"
grep -q '^KV_MEM=' "$ENVF" || echo "KV_MEM=$KVMEM" >> "$ENVF"
grep -q '^CG=' "$ENVF" || echo 'CG=8' >> "$ENVF"
if grep -q '^PYTORCH_CUDA_ALLOC_CONF=' "$ENVF"; then sed -i 's/^PYTORCH_CUDA_ALLOC_CONF=.*/PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True/' "$ENVF"; else echo 'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True' >> "$ENVF"; fi
echo 'VLLM_NO_USAGE_STATS=1' >> "$ENVF"
docker run -d --name "$NAME" --gpus '"device=4"' --network host --env-file "$ENVF" \
  -v /data/models:/data/models:ro -v /data/sandbox/ab-vllm/repo/models:/app/models:rw -v "$CACHE:/cache:rw" \
  nvidia-4090-llm-inference:0.27.1-cu129 single
echo "CACHE=$CACHE"; echo "ENVF=$ENVF"

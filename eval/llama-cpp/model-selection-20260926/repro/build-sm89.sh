#!/usr/bin/env bash
# RUNTIME-CUDA13-SM89 local build: llama.cpp master pinned SHA, CUDA 13.0, sm_89 (RTX 4090).
# Compiles inside a CUDA 13.0.1 devel container (requires cuda>=13.0; host driver provides 13.0).
# Usage: build-sm89.sh [source_sha]
set -euo pipefail
SRC_SHA="${1:-171e8846b4af9766c354064cb776cb34a50f053f}"
B=/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/build
mkdir -p "$B"
docker run --rm \
  -v "$B":/build \
  docker.m.daocloud.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 \
  bash -exc '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends git cmake build-essential libcurl4-openssl-dev >/dev/null
    if [ ! -d /src/.git ]; then git clone --quiet https://github.com/ggml-org/llama.cpp /src; fi
    git -C /src fetch --quiet origin master && git -C /src checkout --quiet '"$SRC_SHA"'
    echo "BUILDING llama.cpp $(git -C /src rev-parse HEAD)"
    cmake -S /src -B /build/out -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DLLAMA_CURL=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs" -DCMAKE_SHARED_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs"
    cmake --build /build/out -j "$(nproc)" --target llama-server
    /build/out/bin/llama-server --version || true
    echo SHA $(git -C /src rev-parse HEAD) > /build/BUILD-SHA.txt
  '
echo "COMPILE DONE $(date -Is)"
# stage runtime image mirroring prod layout: CUDA 13.0 runtime base + /app binaries
cat > "$B/Dockerfile.sm89" <<EOF
FROM docker.m.daocloud.io/nvidia/cuda:13.0.1-runtime-ubuntu24.04
COPY out/bin /app
WORKDIR /app
ENV LD_LIBRARY_PATH=/app
ENTRYPOINT ["/app/llama-server"]
EOF
docker build -t "local/llama.cpp:master-${SRC_SHA:0:12}-cuda13-sm89" "$B"
docker image inspect "local/llama.cpp:master-${SRC_SHA:0:12}-cuda13-sm89" --format 'IMAGE {{.Id}}'
echo "BUILD DONE $(date -Is)"

#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq cmake libnuma-dev make >/tmp/apt.out
cmake -S /src -B /out \
  -DMAKE_WHL_X86=ON -DUSE_CUDA=ON -DUSE_NUMAS=ON \
  -DCUDA_ARCH=89-real -DCMAKE_CUDA_ARCHITECTURES=89-real \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_FLAGS="--split-compile=2"
cmake --build /out --target fastllm_tools -j12
ls -lh /out/tools/ftllm/libfastllm_tools.so
sha256sum /out/tools/ftllm/libfastllm_tools.so

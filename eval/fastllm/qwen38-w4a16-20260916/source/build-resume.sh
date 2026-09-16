#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq cmake libnuma-dev make cuda-libraries-dev-12-9 \
  libnccl2=2.31.2-1+cuda12.9 libnccl-dev=2.31.2-1+cuda12.9 >/tmp/apt.out
cmake --build /out --target fastllm_tools -j12
ls -lh /out/tools/ftllm/libfastllm_tools.so
sha256sum /out/tools/ftllm/libfastllm_tools.so

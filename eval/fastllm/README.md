# FastLLM replacement qualification — 2026-09-15

Scope: determine whether FastLLM can replace the vLLM high-speed lane while llama.cpp production remains frozen.

## Stable wheel compatibility result

Isolated environment: `/data/sandbox/fastllm-qual-20260915/venv`, package `ftllm==0.1.8.2`.

Target: the same production `Qwen3.8-27B-coding-v1.1-W4A16` AutoRound/compressed-tensors checkpoint used by vLLM.

GPU4 target-only smoke failed during model loading with repeated:

`FastLLM Error: SafeTensorItem.CreateBuffer: unsupport src dtype I32`

Verdict: **stable `ftllm 0.1.8.2` cannot directly load the current production W4A16 checkpoint**. This is a checkpoint compatibility failure, not a performance or quality verdict. GPU4 returned to idle after termination; production services were untouched.

## Current-source lane

A pinned upstream FastLLM source snapshot is staged at `/data/sandbox/fastllm-qual-20260915/src`.

- FastLLM commit: `74d36383312421e8316501aa46f7c002c8e490d9`
- pybind11 submodule commit: `0e2c3e5db41b6b2af4038734c84ab855ccaaa5f0`
- build target: `fastllm_tools`, CUDA 12.9 build container, RTX 4090 SM89 only
- first build reached CUDA compilation and failed only because the runtime image lacked `cublas_v2.h`; an isolated resume build adds `cuda-libraries-dev-12-9`.

Current-source compatibility is **pending** until the pinned build completes and the same W4A16 target-only smoke is rerun.

# vLLM 0.28 + CUDA 13 qualification — 2026-09-15

Scope: qualify the CUDA 13 / vLLM 0.28 lane against the current vLLM 0.27.1/cu129 production baseline before using it as the baseline for FastLLM replacement decisions. llama.cpp production is out of scope and remains frozen.

## Frozen environment

- GPU: RTX 4090 24 GB; driver 580.173.02; board power limit 450 W.
- Candidate runtime: `/data/tools/vllm28-env`, vLLM 0.28.0, PyTorch 2.13.0+cu130, `torch.version.cuda=13.0`.
- Target: current production `Qwen3.8-27B-coding-v1.1-W4A16` AutoRound/compressed-tensors checkpoint, including INT8 embed/lm_head.
- Test card: GPU2 only. Production llama.cpp/vLLM cards were not restarted or modified.

## Compatibility result

Stock vLLM 0.28.0 fails while loading the production checkpoint because the packed INT8 embedding is not constructed with the quantization config (`embed_tokens.weight_packed` has no target parameter).

A sandbox overlay applying the existing `inference/vllm/patches/qwen3_5-embed-quant.patch` logic to Qwen3.5 `VocabParallelEmbedding` fixes the target-model load. Patch SHA256: `0a1b9ca06798c1aef582995de5a0beb3ad9a22a54cdbd2361986563a9c7a980e`.

Result: **target-only compatibility PASS**. The model loads 7/7 weight shards and reaches API ready with the optimized compile/CUDA-graph path.

## First comparable target-only measurement

Harness: existing `inference/vllm/bench/ulmus_validate.py`, p565/g512 streaming decode fixture, temperature 0, seed 4242, three measured requests; no speculative decoder.

- decode runs: 57.5033 / 57.9550 / 57.9536 tok/s
- decode median: **57.9536 tok/s**
- 4K prefill fixture: 4,129 actual prompt tokens, **2887.23 tok/s**
- approximate compile time observed: 39.5 s; full engine initialization: ~114 s

The benchmark helper's board-power sampler queries the first visible GPU rather than GPU2, so its reported power fields are invalid for this run and are deliberately excluded from the qualification result.

## Interpretation

57.95 tok/s is a **target-only engine/runtime datum**. It must not be compared directly with the current ~130 tok/s production figure because that figure uses DFlash2 k=7. The purpose of this result is to isolate the 0.28/cu130 base runtime.

The replacement baseline is therefore two-tiered:

1. vLLM 0.27.1/cu129, same target, target-only, same fixture.
2. vLLM 0.28/cu130, production-shaped DFlash2 configuration after required patch migration.

FastLLM must beat the strongest deployable vLLM result, not merely the legacy 0.27.1/cu129 stack.

## Current task / next task

- Current: obtain vLLM 0.27.1/cu129 target-only p565/g512 on the same cards/fixture and normalize vision residency/power policy.
- Next: migrate the minimum DFlash2-required patches to the 0.28 sandbox and qualify p565/g512, long-context and safety.
- Then: use the best deployable vLLM result as the FastLLM replacement threshold.
- No production configuration change is authorized by this report.

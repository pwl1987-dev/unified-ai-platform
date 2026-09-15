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

## Same-card vLLM 0.27.1/cu129 target-only baseline

The exact same target, GPU2, 32K max context, max-seqs=1, prefix-cache setting and p565/g512 harness were then run on the current 0.27.1/cu129 image without speculative decoding.

- decode runs: 57.6851 / 57.6894 / 57.6843 tok/s
- decode median: **57.6851 tok/s**
- 4K prefill fixture: 4,129 actual prompt tokens, **2887.34 tok/s**
- engine init: ~163 s total; torch.compile ~86.9 s

Against 0.28/cu130, target-only decode changes from 57.6851 to 57.9536 tok/s (**+0.47%**); prefill is effectively identical. The material observed improvement is startup/compile time: ~163 s -> ~114 s.

## Native DFlash2 / cu130 — boot 1 qualification

vLLM 0.28 already contains native `DFlash2DraftModel` and the V2 DFlash2 speculator, so the 0.27.1 DFlash2 backport was **not** migrated wholesale. The production recalibrated W4A16 drafter exposed only two demonstrated gaps in the 0.28/cu130 sandbox:

1. compressed-tensors W4A16 `qkv_proj` has no dense `.weight`; DFlash context-K/V precompute therefore needs the existing pack-quantized K/V-row dequantization logic;
2. DFlash2 candidate-selector `flashinfer.top_k` JIT fails under this cu130 environment with a CCCL/toolkit-header mismatch, so this arm forces the selector to `torch.topk`.

With those two minimal compatibility changes plus the existing Qwen3.5 quantized-embedding fix, 0.28/cu130 loads target 7/7 shards + recal drafter 1/1 shard, captures target and DFlash2 CUDA graphs, and reaches API Ready.

32K text-only boot-1 p565/g512 qualification: **141.6137 tok/s median** (141.7234 / 141.6137 / 141.5426); 4K prefill **2883.92 tok/s**. The benchmark delta recorded 236 draft steps, 1652 draft tokens and 530 accepted draft tokens (**32.08% draft-token acceptance**), with accepted positions 175/116/89/58/35/30/27. Raw data: `dflash2-cu130-boot1.json`.

This is a qualification datum, not yet the production verdict: it is 32K + text-only and must survive independent fresh boots before comparison at the 245760 production context/vision shape. Harness power fields remain invalid because the helper samples GPU0; board power is handled separately.

## Fresh-boot repeatability gate

Three independent GPU2 process boots of the same 32K text-only DFlash2 arm produced decode medians **141.6137 / 141.6538 / 141.6070 tok/s**. Mean **141.6248 tok/s**, sample stdev **0.0253 tok/s**; total range **0.0468 tok/s = 0.033% of mean**. Draft-token acceptance was exactly **32.082%** on all three deterministic fixture runs.

Verdict: **PASS — no boot-level bimodality observed in this 3-boot qualification window.** This closes the specific 0.27-era boot-mode concern for the current 32K arm, but does not yet prove the 245760 production shape. Raw files: `dflash2-cu130-boot{1,2,3}.json`; aggregate: `dflash2-cu130-fresh-boots-summary.json`.

## Interpretation

57.95 tok/s is a **target-only engine/runtime datum**. It must not be compared directly with the current ~130 tok/s production figure because that figure uses DFlash2 k=7. The same-card A/B shows that CUDA13/vLLM 0.28 alone does **not** provide a material single-stream decode gain over 0.27.1/cu129; the next decisive test is native DFlash2 on 0.28/cu130.

The replacement baseline is therefore two-tiered:

1. vLLM 0.27.1/cu129, same target, target-only, same fixture.
2. vLLM 0.28/cu130, production-shaped DFlash2 configuration after required patch migration.

FastLLM must beat the strongest deployable vLLM result, not merely the legacy 0.27.1/cu129 stack.

## Current task / next task

- Completed: vLLM 0.27.1/cu129 same-card target-only baseline; decode is effectively tied with 0.28/cu130 (+0.47% for 0.28), while 0.28 starts/compiles materially faster.
- Completed: native DFlash2 + recal W4A16 compatibility and 3-fresh-boot repeatability gate; 32K decode mean 141.625 tok/s with only 0.033% total boot range, no bimodality observed.
- Current: measure the 0.28/cu130 long-context capacity gap against the exact 245760 production target and identify whether KVarN / KV-layout migration is mandatory before performance qualification.
- Next: qualify the minimum long-context memory path, then run 245760 prefix-cache/quality/stability and use the strongest deployable vLLM result as the FastLLM replacement threshold.
- No production configuration change is authorized by this report.

# vLLM 0.27 vs 0.28 — RTX 4090 long-context qualification

> 2026-09-16. Priority: context >=128K, then resident concurrency, accuracy, TTFT.

## Frozen baseline

- Same Qwen3.8-27B coding W4A16 target and recal DFlash2 drafter k=7.
- Single RTX 4090 24GB, text-only, max_model_len=245760, KVarN k4v2_g128, KV=4.82GB, CG=8, max_num_batched_tokens=2048.
- 0.27/cu129 is production-family reference; 0.28/cu130 uses the archived patch + package lock.

## Long-context results

| C | Target | 0.27 TTFT / wall | 0.28 TTFT / wall | max_running | KV peak |
|---:|---:|---:|---:|---:|---:|
| 1 | 224K | 183.44s / 184.49s | 150.80s / 151.65s | 1/1 | 95.43% |
| 1 | 240K | 203.65s / 204.76s | 166.82s / 168.18s | 1/1 | 99.70% |
| 2 | 128K | 127.83s / 171.54s | 108.74s / 150.11s | 1/1 | 68.60% |

- C1 224K and 240K pass on both versions with zero preemption.
- 240K is a verified boundary, not the preferred daily profile: KV is ~99.7%.
- C2@128K is admitted safely but is not true dual-resident execution; both versions only reach max_running=1.

## Long-context accuracy

Random five-needle v2 uses non-pattern values at about 10/30/50/70/90% of the context. Both versions pass 5/5 exactly.

| Prompt | 0.27 | 0.28 |
|---:|---|---|
| 127011 | PASS, TTFT 82.83s | PASS, TTFT 84.38s |
| 223011 | PASS, TTFT 182.09s | PASS, TTFT 186.20s |
| 239011 | PASS, TTFT 202.84s | PASS, TTFT 206.28s |

## Resident concurrency evidence

At ~4K/request, both versions reach resident C4. C6/C8 submissions complete but max_running remains 4. This is physical-resident evidence, not the recommended development profile because context length has higher priority.

## Current deployment interpretation

- Minimum acceptable development boundary: >=128K.
- Main candidate: ~224K C1, pending repeated fresh-boot/cross-GPU TTFT reconciliation.
- 240K: capacity + accuracy boundary only; insufficient KV headroom for a preferred daily profile.
- C2@128K: useful admission/queue behavior, not true two-request resident concurrency.

## Evidence / reproducibility

- `raw/valid/`: accepted matrix, resident, and accuracy-v2 JSON/stdout.
- `raw/invalid/accuracy-v1/`: preserved invalid fixture; output truncation and inferable needle pattern make it non-authoritative.
- `raw/historical/`: earlier comparison/failure evidence.
- `repro/`: exact probes, captured launchers, sanitized env/package manifests, model hashes.
- Patch: `inference/vllm/build/cu130-driver580/vllm028-kvarn-dflash2-w4a16.patch`.

Do not compare FastLLM against a lower-context shortcut: it must first pass the same >=128K, random-five-needle, TTFT, and stability gates.

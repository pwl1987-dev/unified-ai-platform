# FastLLM Qwen3.8 W4A16 qualification — 2026-09-16

Status: **archived / not selected for deployment**. This directory is retained as a future regression baseline, not as a production recipe.

## Frozen identity
- Upstream FastLLM pin: `74d36383312421e8316501aa46f7c002c8e490d9`.
- Qualification runtime was a CUDA 13 / SM89 source build plus a local W8-group128 loader probe for `embed_tokens` and `lm_head`.
- Current-source native library SHA256: `e29752af9e353bd39eb2adf6202f57b437ad29215c94506c07198d173be3f445`.
- Stable `ftllm==0.1.8.2` native library SHA256: `0d386f46b4e7ee8b9e5f3f57cdf10e823a31ae5a9097dadc4ccf278b6284f857`.
- Model: Qwen3.8-27B coding v1.1 AutoRound W4A16, same target used by the vLLM qualification.

## Valid current-source findings
| Shape | Result |
|---|---|
| TP1 8K smoke | PASS after W8/F16 loader probe |
| TP1 128K FP4 KV | OOM during warmup; not deployable |
| TP2 128K C1 | PASS; 127,011-token random 5-needle = 5/5 |
| TP2 127K TTFT | 119.95 s; ~55.0 decode tok/s |
| TP4 128K C1 | PASS; 127,011-token random 5-needle = 5/5 |
| TP4 127K TTFT | 88.93 s; ~73.7 decode tok/s |
| TP3 / TP5 / TP6 128K C1 | FAIL in I32/allocator load path |
| TP2 / TP4 131,200 tokens | FAIL; 131,072 was the highest demonstrated service window |
| TP2 max_batch=2 at 64K | FAIL during service startup |

## Decision
FastLLM was not selected to replace vLLM. On this checkpoint and 8×RTX 4090 PCIe host, the tested source path required local loader work, only TP2/TP4 reached the 128K correctness gate, TP3/5/6 failed, >128K did not start, and TP4 used four GPUs while its 127K TTFT remained slightly slower than the archived single-GPU vLLM 0.27/0.28 reference.

## Evidence hygiene
`raw/fastllm-raw-snapshot.tar.gz` preserves the original experiment files byte-for-byte. Some intermediate commands accidentally resolved to the stable wheel instead of the source probe; those runs are listed in `INVALID-RUNTIME-CONTAMINATION.txt` and must not be used for current-source conclusions. `RESULTS.json` contains the accepted summary. The probe source history is retained as `source/fastllm-probe-source-history.tar.gz`; the 102 MB native binary is intentionally not committed.

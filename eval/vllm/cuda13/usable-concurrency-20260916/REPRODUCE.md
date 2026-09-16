# Reproduce the vLLM 0.27 / 0.28 qualification

This bundle is intended to reproduce the RTX 4090 comparison without relying on the original sandbox.

## Preconditions

- NVIDIA RTX 4090 24GB, driver compatible with CUDA 13.0 for the 0.28 arm.
- Exact target and DFlash2 checkpoints matching `repro/manifests/model-sha256.txt`.
- Python 3.12 + `venv` + `patch` for 0.28; Docker + the archived 0.27 image for 0.27.
- Do not reuse compile caches across different concurrency shapes.

## Verify model identity

Compare the checkpoint files against `repro/manifests/model-sha256.txt` before running any benchmark. `model-paths-reference.txt` records the original paths only as a reference; paths may differ on another host.

## Build the 0.28/cu130 environment

From the repository root:

```bash
VENV=/opt/qwen-vllm028 \
  eval/vllm/cuda13/usable-concurrency-20260916/repro/setup_vllm028.sh
```

The setup script installs the locked packages, performs `patch --dry-run`, applies `inference/vllm/build/cu130-driver580/vllm028-kvarn-dflash2-w4a16.patch`, and imports the KVarN + DFlash2 patched code.
## Start either arm

Set the exact checkpoint directories, then launch only the arm being tested:

```bash
export TARGET_DIR=/path/to/exact/target
export DRAFT_DIR=/path/to/exact/dflash2
GPU=2 PORT=19637 MAX_SEQS=1 VENV=/opt/qwen-vllm028 \
  eval/vllm/cuda13/usable-concurrency-20260916/repro/start_vllm028.sh
```

For 0.27, use `start_vllm027.sh` and set `IMAGE` if the archived image has another local tag. Both launchers freeze `max_model_len=245760`, KVarN k4v2_g128, KV=4.82GB, DFlash2 k=7, CG=8, prefix cache, mamba align, and 2048 batched tokens.

## Run the evidence probes

Use `long_concurrency_probe_v4.py` for capacity/admission tests and `captured/long_multineedle_probe_v2.py` for long-context accuracy. Use a unique cache salt per request and keep the exact prompt/token targets in the raw evidence.

Primary decision points are C1 224K/240K, C2 128K, and random five-needle accuracy near 127K/223K/239K. The ~4K C4/C6/C8 data is retained only to establish the physical resident ceiling.

## Evidence policy

`raw/valid/` is authoritative. `raw/invalid/accuracy-v1/` is intentionally preserved but must not be used for conclusions. `raw/historical/` records earlier experiments/failures. `SUMMARY.json` is machine-readable and `REPORT.md` is the current interpretation.

FastLLM must use these same context, accuracy, TTFT, and stability gates before it can be considered a replacement.

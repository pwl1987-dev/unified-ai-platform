#!/usr/bin/env python3
"""Phase 03 FP8C — KV-only calibrated artifact 构建（在 fp8c-build 隔离容器 venv 内执行）。

官方通路（P0A.4 探针实证）：compressed-tensors checkpoint 侧 kv_cache_scheme + 每层
k/v_scale 参数（vLLM CompressedTensorsKVCacheMethod 装载）；llm-compressor
QuantizeModifier 仅带 kv_cache_scheme、无 weight/activation scheme → W4A16 pack 权重不动。

契约（gates-phase03 calibration_contract）：
  - 前置：overlap-check.json verdict==PASS（校准/评测隔离）否则中止
  - 校准语料：fixtures/calibration/phase03-corpus（64 样本，独立生成器，非评测族）
  - 输出：新目录 immutable artifact（绝不写 parent 目录）
  - provenance：全字段落盘（dataset/recipe/toolchain/tokenizer/strategy）
  - KV-only 不成立（库强制重量化/报错）→ 记录错误退出码 3 = FP8C_KV_ONLY_UNSUPPORTED，
    不打补丁绕过（用户契约 #2/#4）。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PARENT = "/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128"
NG = Path("/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917")
CORPUS = NG / "fixtures/calibration/phase03-corpus/samples.jsonl"
CORPUS_MAN = NG / "fixtures/calibration/phase03-corpus-manifest.json"
OVERLAP = NG / "fixtures/calibration/overlap-check.json"
OUT = Path("/data/sandbox/nextgen-20260917/fp8c-artifact/ph3-fp8c-kv-e4m3-pt")
PROV = Path("/data/sandbox/nextgen-20260917/fp8c-build/fp8c-build-provenance.json")
MAX_SEQ = 8192
N_SAMPLES = 64


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    oc = json.loads(OVERLAP.read_text())
    if oc.get("verdict") != "PASS":
        print("ABORT: calibration/eval overlap check not PASS", file=sys.stderr)
        return 2
    cm = json.loads(CORPUS_MAN.read_text())

    import importlib.metadata as md
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import QuantizationModifier
    from compressed_tensors.quantization import QuantizationArgs

    # KV-only：仅 kv_cache_scheme（k/v 激活输出 absmax→FP8 per-tensor scale），
    # 无 scheme/weights/activations —— pack 权重与 W4A16 结构不动（verify 脚本证明）
    scheme = QuantizationArgs(num_bits=8, type="float", symmetric=True,
                              strategy="tensor", observer="minmax")
    recipe = [QuantizationModifier(kv_cache_scheme=scheme)]
    recipe_repr = ("QuantizationModifier(kv_cache_scheme=QuantizationArgs("
                   "num_bits=8, type=float, symmetric=True, strategy=tensor, "
                   "observer=minmax)) — no weight/activation schemes（KV-only 单变量）")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"[fp8c] oneshot: parent={PARENT}\n[fp8c] corpus={CORPUS} ({N_SAMPLES} samples, max_seq={MAX_SEQ})",
          flush=True)
    try:
        oneshot(
            model=PARENT,
            dataset=str(CORPUS),
            text_column="text",
            recipe=recipe,
            num_calibration_samples=N_SAMPLES,
            max_seq_length=MAX_SEQ,
            output_dir=str(OUT),
            trust_remote_code_model=True,
        )
    except Exception as e:  # noqa: BLE001 —— 记录后按契约归 UNSUPPORTED，不绕过
        err = {"error_type": type(e).__name__, "error": repr(e)[-4000:]}
        PROV.write_text(json.dumps({"status": "FP8C_KV_ONLY_UNSUPPORTED",
                                    "oneshot_error": err}, indent=1))
        print(f"[fp8c] FP8C_KV_ONLY_UNSUPPORTED: {err['error_type']}", file=sys.stderr)
        return 3

    # artifact 文件清单
    files = {}
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(OUT))] = {"sha256": sha256_file(p),
                                              "bytes": p.stat().st_size}
    tok_files = {}
    for name in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                 "chat_template.jinja", "vocab.json", "merges.txt", "tokenizer.model"):
        pp = PARENT / name
        if pp.exists():
            tok_files[name] = sha256_file(pp)
    prov = {
        "status": "BUILT",
        "built_utc": __import__("datetime").datetime.now().astimezone().isoformat(),
        "parent_model_path": PARENT,
        "parent_config_sha256": sha256_file(Path(PARENT) / "config.json"),
        "artifact_dir": str(OUT),
        "artifact_manifest": files,
        "calibration_dataset_sha256": cm["dataset_sha256"],
        "calibration_sample_count": cm["sample_count"],
        "calibration_seed": cm["seed"],
        "max_seq_len": MAX_SEQ,
        "recipe_sha256": hashlib.sha256(
            (Path(__file__).read_bytes()).hexdigest().encode() + recipe_repr.encode()
        ).hexdigest(),
        "recipe": recipe_repr,
        "build_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "calibration_toolchain": {
            "llm-compressor": md.version("llm-compressor"),
            "compressed-tensors": md.version("compressed-tensors"),
            "torch": md.version("torch"),
            "transformers": md.version("transformers"),
            "python": sys.version.split()[0],
        },
        "tokenizer_files_sha256": tok_files,
        "strategy": "per-tensor",
        "environment": "Docker python:3.12-slim + uv venv（fp8c-build 容器，CDI GPU3；vllm29-env 零写入）",
    }
    PROV.write_text(json.dumps(prov, indent=1, ensure_ascii=False))
    print(f"[fp8c] artifact written: {OUT} ({len(files)} files)")
    print(f"[fp8c] provenance: {PROV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

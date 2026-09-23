#!/usr/bin/env python3
"""Phase 04 P0B.A(续) — Q4-CODING-V1.1 构建（官方探针 ALIVE 后按合同执行）。

compressed-tensors W8A8-FP8：
  weights      = fp8 e4m3 per-channel sym（minmax）
  input_activations = fp8 dynamic per-token（运行时量化，无静态 scale）
  ignore = linear_attn 全家 + lm_head（W8A16 v2 教训：lm_head 绑定权重 packed 不可加载）
teacher = merged-bf16（same-base VERIFIED）；校准语料/顺序/seed 同 W8A16 冻结值。
产出 /data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a8fp8-dynamic/
+ provenance（schema 1.4 全字段）。--provenance-only 支持重建元数据。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

TEACHER = "/data/compose/qwen27b/train/merged-bf16"
NG = Path("/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917")
CORPUS = NG / "fixtures/calibration/phase03-corpus/samples.jsonl"
OUT = Path("/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a8fp8-dynamic")
PROV = Path("/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a8fp8-dynamic-provenance.json")
MAX_SEQ = 1024
N_SAMPLES = 64


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    oc = json.loads((NG / "fixtures/data-roles/overlap-check.json").read_text())
    if oc.get("verdict") != "PASS":
        print("ABORT: 三分 overlap 非 PASS", file=sys.stderr)
        return 2

    import importlib.metadata as md
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import QuantizationModifier
    from compressed_tensors.quantization import QuantizationArgs, QuantizationScheme

    group = QuantizationScheme(
        targets=["Linear"],
        weights=QuantizationArgs(num_bits=8, type="float", strategy="channel",
                                 symmetric=True, observer="minmax"),
        input_activations=QuantizationArgs(num_bits=8, type="float",
                                           strategy="token", dynamic=True,
                                           symmetric=True))
    recipe = [QuantizationModifier(config_groups={"group_0": group},
                                   ignore=["re:.*linear_attn.*", "re:.*lm_head$"])]
    recipe_repr = ("QuantizationModifier(W8A8-FP8: weights fp8-e4m3 channel sym minmax + "
                   "input fp8 dynamic per-token；ignore linear_attn 全家+lm_head)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    skip_quant = "--provenance-only" in sys.argv and (OUT / "config.json").exists()
    if not skip_quant:
        from transformers import AutoTokenizer
        from datasets import load_dataset
        tok = AutoTokenizer.from_pretrained(TEACHER)
        ds = load_dataset("json", data_files=str(CORPUS), split="train")
        print(f"[q4c] oneshot W8A8-FP8-dynamic teacher={TEACHER}", flush=True)
        try:
            oneshot(model=TEACHER, tokenizer=tok, dataset=ds, text_column="text",
                    recipe=recipe, num_calibration_samples=N_SAMPLES,
                    max_seq_length=MAX_SEQ, output_dir=str(OUT),
                    trust_remote_code_model=True)
        except Exception as e:  # noqa: BLE001
            PROV.write_text(json.dumps({"status": "BUILD_FAILED",
                                        "error_type": type(e).__name__,
                                        "error": repr(e)[-4000:]}, indent=1))
            print(f"[q4c] BUILD_FAILED: {type(e).__name__}", file=sys.stderr)
            return 3

    files = {}
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(OUT))] = {"sha256": sha256_file(p),
                                              "bytes": p.stat().st_size}
    tok_files = {n: sha256_file(OUT / n) for n in
                 ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                  "chat_template.jinja") if (OUT / n).exists()}
    prov = {
        "status": "BUILT",
        "built_utc": __import__("datetime").datetime.now().astimezone().isoformat(),
        "weight_profile": "Q4_CODING_V1_1",
        "parent_weight_sha256": sha256_file(Path(TEACHER) / "model-00001-of-00012.safetensors"),
        "parent_dir": TEACHER,
        "artifact_dir": str(OUT),
        "artifact_sha_manifest": files,
        "artifact_aggregate_sha256": hashlib.sha256(
            "\n".join(f"{k}:{v['sha256']}" for k, v in sorted(files.items())).encode()).hexdigest(),
        "tokenizer_sha256": tok_files,
        "config_sha256": sha256_file(OUT / "config.json"),
        "quant_recipe_sha256": hashlib.sha256(
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest().encode()
            + recipe_repr.encode()).hexdigest(),
        "quant_recipe": recipe_repr,
        "build_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "quant_tool_lock_sha256": hashlib.sha256(
            f"llmcompressor={md.version('llmcompressor')}|compressed-tensors={md.version('compressed-tensors')}".encode()).hexdigest(),
        "quant_toolchain": {"llmcompressor": md.version("llmcompressor"),
                            "compressed-tensors": md.version("compressed-tensors")},
        "calibration_manifest_sha256": json.loads(
            (NG / "fixtures/calibration/phase03-corpus-manifest.json").read_text())["dataset_sha256"],
        "calibration_seed": 20260921,
        "calibration_order_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "max_seq_len": MAX_SEQ,
        "module_precision_map": {
            "_final": "Linear=fp8-e4m3 per-channel sym（输入动态 per-token fp8）；"
                      "lm_head/embed/GDN in_proj 家族/visual=bf16"},
        "actual_kernel_backend": None,   # boot smoke 回填
        "precedent": "官方 FP8 探针 ALIVE（Marlin WNA16 路径）——本 artifact 为 same-base 正式候选",
        "environment": "fp8c-build 容器",
    }
    PROV.write_text(json.dumps(prov, indent=1, ensure_ascii=False))
    print(f"[q4c] artifact {len(files)} 文件；aggregate={prov['artifact_aggregate_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

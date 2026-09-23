#!/usr/bin/env python3
"""Phase 04 P0B.B — W8A16 g128 same-base artifact 构建（容器内执行）。

gates-phase04 build_contract.w8a16_recipe_frozen：
  teacher = merged-bf16（VERIFIED_LINEAGE，52G）
  scheme  = int8 g128 sym group（W8A16 pack-quantized，Marlin 服务路径同 Q0 家族）
  calib   = quant_calib_sensitivity_dev（phase03-corpus 64 样本，seed 20260921，文件序）
  max_seq = 1024（TRAIN-NOTES 层0 OOM 教训：2048→1024）
输出：/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a16-g128/（immutable）
provenance：schema 1.4 quant_provenance 全字段（11 项）。
退出码：0=建成；3=构建失败（如实记录，不绕过）。
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
OUT = Path("/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a16-g128")
PROV = Path("/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a16-g128-provenance.json")
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
    corpus_bytes = CORPUS.read_bytes()
    order_sha = hashlib.sha256(corpus_bytes).hexdigest()   # 文件序确定性（禁 shuffle）

    import importlib.metadata as md
    import torch
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import QuantizationModifier
    from compressed_tensors.quantization import QuantizationArgs, QuantizationScheme

    # llmcompressor 0.12 契约：自定义 scheme 走 config_groups（scheme 参数只收 preset 名）
    # ignore：GDN in_proj 保 bf16（Q0 精度政策）+ lm_head 排除（架构为绑定权重，
    # 无独立模块参数——v2 构建实证 lm_head.weight_packed 不可加载，Q0 的 int8 头
    # 依赖 serving 树补丁基建，W8A16 准上界走无补丁依赖的 bf16 头）
    group = QuantizationScheme(
        targets=["Linear"],
        weights=QuantizationArgs(num_bits=8, group_size=128, strategy="group",
                                 symmetric=True, observer="minmax"))
    recipe = [QuantizationModifier(config_groups={"group_0": group},
                                   ignore=["re:.*linear_attn.*", "re:.*lm_head$"])]
    recipe_repr = ("QuantizationModifier(scheme=int8 g128 sym group minmax, targets=[Linear]) "
                   "——W8A16，无 activation scheme；同 Q0 家族 pack-quantized/Marlin 服务路径")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"[w8a16] oneshot teacher={TEACHER} calib=64 样本 max_seq={MAX_SEQ}", flush=True)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TEACHER)
    from datasets import load_dataset
    skip_quant = "--provenance-only" in sys.argv and (OUT / "config.json").exists()
    if not skip_quant:
        ds = load_dataset("json", data_files=str(CORPUS), split="train")
        try:
            oneshot(model=TEACHER, tokenizer=tok, dataset=ds, text_column="text",
                    recipe=recipe, num_calibration_samples=N_SAMPLES,
                    max_seq_length=MAX_SEQ, output_dir=str(OUT),
                    trust_remote_code_model=True)
        except Exception as e:  # noqa: BLE001
            PROV.write_text(json.dumps({"status": "BUILD_FAILED",
                                        "error_type": type(e).__name__,
                                        "error": repr(e)[-4000:]}, indent=1))
            print(f"[w8a16] BUILD_FAILED: {type(e).__name__}", file=sys.stderr)
            return 3
    else:
        print("[w8a16] --provenance-only：跳过重量化，重建 provenance")

    files = {}
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(OUT))] = {"sha256": sha256_file(p),
                                              "bytes": p.stat().st_size}
    cfg_out = json.loads((OUT / "config.json").read_text())
    qc = cfg_out.get("quantization_config") or {}
    groups = qc.get("config_groups") or {}
    module_map = {"_summary": {}}
    for gname, g in groups.items():
        w = (g or {}).get("weights") or {}
        module_map["_summary"][gname] = {
            "targets": g.get("targets"), "bits": w.get("num_bits"),
            "group": w.get("group_size"), "symmetric": w.get("symmetric")}
    module_map["_ignore_count"] = len(qc.get("ignore", []))
    module_map["_kv_cache_scheme"] = qc.get("kv_cache_scheme", "absent")
    module_map["_declared"] = "Linear=int8 g128 sym；其余（visual/GDN in_proj/lm_head/embed 由 teacher config 继承或 ignore）"

    tok_files = {}
    for name in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                 "chat_template.jinja"):
        pp = OUT / name
        if pp.exists():
            tok_files[name] = sha256_file(pp)
    prov = {
        "status": "BUILT",
        "built_utc": __import__("datetime").datetime.now().astimezone().isoformat(),
        "weight_profile": "W8A16_SAME_BASE",
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
            f"llmcompressor={md.version('llmcompressor')}|compressed-tensors={md.version('compressed-tensors')}"
            f"|torch={md.version('torch')}|transformers={md.version('transformers')}".encode()).hexdigest(),
        "quant_toolchain": {"llmcompressor": md.version("llmcompressor"),
                            "compressed-tensors": md.version("compressed-tensors"),
                            "torch": md.version("torch"),
                            "transformers": md.version("transformers"),
                            "python": sys.version.split()[0]},
        "calibration_manifest_sha256": json.loads(
            (NG / "fixtures/calibration/phase03-corpus-manifest.json").read_text())["dataset_sha256"],
        "calibration_seed": 20260921,
        "calibration_order_sha256": order_sha,
        "max_seq_len": MAX_SEQ,
        "module_precision_map": module_map,
        "actual_kernel_backend": None,   # boot smoke 时回填（预期 MarlinLinearKernel）
        "environment": "fp8c-build 容器（Docker+UV 隔离；vllm29-env 零写入）",
    }
    PROV.write_text(json.dumps(prov, indent=1, ensure_ascii=False))
    print(f"[w8a16] artifact {len(files)} 文件；aggregate={prov['artifact_aggregate_sha256'][:16]}…")
    print(f"[w8a16] provenance -> {PROV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

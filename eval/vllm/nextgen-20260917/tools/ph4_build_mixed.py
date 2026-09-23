#!/usr/bin/env python3
"""Phase 04 P1 — Q1/Q2 分层混合 artifact 构建（消费 q1q2-recipe-proposal.json）。

多 config_groups（每族独立 bits/gsize）+ 精确模块名 targets + 全局 ignore
（linear_attn 全家 + lm_head——绑定权重教训）。teacher=merged-bf16（same-base）。
产出 /data/sandbox/nextgen-20260917/quant-artifacts/ph4-{q1,q2}-mixed/
+ 各自 provenance（schema 1.4 全字段 + proposal_sha 绑定）。
用法：ph4_build_mixed.py q1|q2 [--provenance-only]
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
PROPOSAL = NG / "raw/staging/PH4-P1/q1q2-recipe-proposal.json"
MAX_SEQ = 1024
N_SAMPLES = 64
ART = Path("/data/sandbox/nextgen-20260917/quant-artifacts")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def scheme(bits: int, group: int):
    from compressed_tensors.quantization import QuantizationArgs, QuantizationScheme
    return QuantizationScheme(
        targets=["Linear"],
        weights=QuantizationArgs(num_bits=bits, group_size=group,
                                 strategy="group", symmetric=True,
                                 observer="minmax"))


def build(which: str) -> int:
    prop = json.loads(PROPOSAL.read_text())
    sens = json.loads((NG / "raw/staging/PH4-P1/layer-sensitivity.json").read_text())
    rows = {r["module"]: r for r in sens["rows"]}
    OUT = ART / f"ph4-{which}-mixed"
    PROV = ART / f"ph4-{which}-mixed-provenance.json"

    def mods(pred):
        return [m for m, r in rows.items() if pred(r)]

    if which == "q1":
        groups_def = [
            ("mlp_w4", mods(lambda r: r["family"] in ("mlp.gate", "mlp.up", "mlp.down")), (4, 128)),
            # 高敏族（mlp.gate/up 50% 贡献）升 g64；attn.q 高敏第三位同升
            ("sens_g64", mods(lambda r: r["family"] in ("mlp.gate", "mlp.up", "attn.q")), (4, 64)),
            ("firstlast_w8", mods(lambda r: r["layer"] in (0, 1, 62, 63)), (8, 128)),
        ]
    else:  # q2
        groups_def = [
            ("mlp_w4", mods(lambda r: r["family"] in ("mlp.gate", "mlp.up", "mlp.down")), (4, 128)),
            ("attn_w8", mods(lambda r: r["family"].startswith("attn.")), (8, 128)),
            ("gdn_out_g64", mods(lambda r: r["family"] == "gdn.out_proj"), (4, 64)),
        ]
    # 去重优先级：后组覆盖前组（更细粒度规则优先）
    assigned: dict[str, tuple[int, int]] = {}
    for gname, mlist, bw in groups_def:
        for m in mlist:
            assigned[m] = bw
    final_groups: dict[tuple[int, int], list[str]] = {}
    for m, bw in assigned.items():
        final_groups.setdefault(bw, []).append(m)

    import importlib.metadata as md
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import QuantizationModifier
    cfg_groups = {f"g{bits}_{grp}": (lambda t, b, g: __import__("types").SimpleNamespace(
        scheme=scheme(b, g), targets=t))(sorted(mlist), bits, grp)
        for (bits, grp), mlist in final_groups.items()}
    recipe_mods = []
    for gname, gs in cfg_groups.items():
        recipe_mods.append((gname, gs.scheme, gs.targets))
    recipe = [QuantizationModifier(
        config_groups={g: s for g, s, _ in recipe_mods},
        ignore=["re:.*linear_attn.*", "re:.*lm_head$"])]
    pmap = {g: {"n_modules": len(t), "bits": s.weights.num_bits,
                "group": s.weights.group_size}
            for g, s, t in recipe_mods}
    recipe_repr = json.dumps({g: {"bits": s.weights.num_bits,
                                  "group": s.weights.group_size,
                                  "n": len(t)} for g, s, t in recipe_mods}) \
        + "|ignore=linear_attn+lm_head"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    skip = "--provenance-only" in sys.argv and (OUT / "config.json").exists()
    if not skip:
        from transformers import AutoTokenizer
        from datasets import load_dataset
        tok = AutoTokenizer.from_pretrained(TEACHER)
        ds = load_dataset("json", data_files=str(CORPUS), split="train")
        print(f"[{which}] oneshot groups={list(pmap)}", flush=True)
        try:
            oneshot(model=TEACHER, tokenizer=tok, dataset=ds, text_column="text",
                    recipe=recipe, num_calibration_samples=N_SAMPLES,
                    max_seq_length=MAX_SEQ, output_dir=str(OUT),
                    trust_remote_code_model=True)
        except Exception as e:  # noqa: BLE001
            PROV.write_text(json.dumps({"status": "BUILD_FAILED",
                                        "error_type": type(e).__name__,
                                        "error": repr(e)[-4000:]}, indent=1))
            print(f"[{which}] BUILD_FAILED: {type(e).__name__}", file=sys.stderr)
            return 3

    files = {str(p.relative_to(OUT)): {"sha256": sha256_file(p), "bytes": p.stat().st_size}
             for p in sorted(OUT.rglob("*")) if p.is_file()}
    prov = {
        "status": "BUILT",
        "built_utc": __import__("datetime").datetime.now().astimezone().isoformat(),
        "weight_profile": f"Q{'1' if which=='q1' else '2'}_MIXED",
        "parent_weight_sha256": sha256_file(Path(TEACHER) / "model-00001-of-00012.safetensors"),
        "parent_dir": TEACHER,
        "artifact_dir": str(OUT),
        "artifact_sha_manifest": files,
        "artifact_aggregate_sha256": hashlib.sha256(
            "\n".join(f"{k}:{v['sha256']}" for k, v in sorted(files.items())).encode()).hexdigest(),
        "tokenizer_sha256": {n: sha256_file(OUT / n) for n in
                             ("tokenizer.json", "tokenizer_config.json") if (OUT / n).exists()},
        "config_sha256": sha256_file(OUT / "config.json"),
        "quant_recipe_sha256": hashlib.sha256(recipe_repr.encode()).hexdigest(),
        "quant_recipe": recipe_repr[:2000],
        "build_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "proposal_sha256": hashlib.sha256(PROPOSAL.read_bytes()).hexdigest(),
        "sensitivity_basis": {"rows": len(sens["rows"]),
                              "skipped": len(sens.get("skipped", []))},
        "quant_tool_lock_sha256": hashlib.sha256(
            f"llmcompressor={md.version('llmcompressor')}".encode()).hexdigest(),
        "quant_toolchain": {"llmcompressor": md.version("llmcompressor")},
        "calibration_manifest_sha256": json.loads(
            (NG / "fixtures/calibration/phase03-corpus-manifest.json").read_text())["dataset_sha256"],
        "calibration_seed": 20260921,
        "calibration_order_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "max_seq_len": MAX_SEQ,
        "module_precision_map": pmap,
        "actual_kernel_backend": None,
        "environment": "fp8c-build 容器",
    }
    PROV.write_text(json.dumps(prov, indent=1, ensure_ascii=False))
    print(f"[{which}] {len(files)} 文件 aggregate={prov['artifact_aggregate_sha256'][:16]}… "
          f"groups={ {g: p['n_modules'] for g, p in pmap.items()} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(build(sys.argv[1].lower() if len(sys.argv) > 1 else "q1"))

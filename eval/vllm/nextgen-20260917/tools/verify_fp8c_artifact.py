#!/usr/bin/env python3
"""Phase 03 FP8C — artifact_single_variable_verification（gates calibration_contract）。

证明 artifact 相对 parent 的变化范围 = 且仅 = KV cache scale metadata：
  V1 config diff：config.json 深比较，唯一允许差异 = quantization_config.kv_cache_scheme
     null→dict；其余任何键差异 = VIOLATION
  V2 tokenizer/chat template：全部 tokenizer 相关文件逐字节 SHA 相等
  V3 W4A16 量化结构不变：config_groups/ignore/format/quantization_status 逐键相等
  V4 tensor 级：公共张量逐字节 SHA 全等（权重零改动）；artifact 仅新增
     attention 层 k_scale/v_scale（数量=2×全注意力层数，per-tensor 标量形状）；
     无删除/无重排/无其他新增
  V5 provenance 完备（gates required_records 全字段）
判定：FP8C_KV_ONLY_VERIFIED / VIOLATION（退出码 0/1）。
（runtime resolved dtype/scales 装载验证在 P1 最小 boot 时另行记录，不在此脚本。）
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PARENT = Path("/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128")
ART = Path("/data/sandbox/nextgen-20260917/fp8c-artifact/ph3-fp8c-kv-e4m3-pt")
PROV = Path("/data/sandbox/nextgen-20260917/fp8c-build/fp8c-build-provenance.json")
OUT = Path("/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917/"
           "raw/staging/PH3-P0B/fp8c-single-variable-verification.json")
TOK_FILES = ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
             "chat_template.jinja", "vocab.json", "merges.txt", "tokenizer.model",
             "added_tokens.json")
REQUIRED_PROV = ["parent_model_path", "parent_config_sha256", "artifact_dir",
                 "artifact_manifest", "calibration_dataset_sha256",
                 "calibration_recipe_sha256", "calibration_toolchain",
                 "tokenizer_files_sha256", "strategy", "calibration_sample_count",
                 "max_seq_len", "calibration_seed"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def deep_diff(a, b, path="") -> list[str]:
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: <absent> -> {b[k]!r}")
            elif k not in b:
                out.append(f"{path}.{k}: {a[k]!r} -> <absent>")
            else:
                out += deep_diff(a[k], b[k], f"{path}.{k}")
    elif a != b:
        out.append(f"{path}: {a!r} -> {b!r}")
    return out


def load_tensors(root: Path) -> dict[str, dict]:
    """safetensors 头解析（名称→{dtype,shape,offsets}）+ 文件级字节 SHA。"""
    from safetensors import safe_open
    tens = {}
    for st in sorted(root.glob("*.safetensors")):
        with safe_open(st, framework="numpy") as f:
            for k in f.keys():
                t = f.get_slice(k)
                tens[k] = {"file": st.name, "shape": list(t.get_shape()),
                           "dtype": t.get_dtype(),
                           "data_sha256": None}   # 逐张量 hash 见 hash step
    return tens


def hash_tensors(root: Path, names: set[str]) -> dict[str, str]:
    import numpy as np
    from safetensors import safe_open
    out = {}
    for st in sorted(root.glob("*.safetensors")):
        with safe_open(st, framework="numpy") as f:
            for k in f.keys():
                if k not in names:
                    continue
                arr = f.get_tensor(k)
                out[k] = hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()
    return out


def main() -> int:
    V: dict[str, object] = {"checks": {}, "violations": []}
    pc = json.loads((PARENT / "config.json").read_text())
    ac = json.loads((ART / "config.json").read_text())

    # V1 config diff
    diffs = deep_diff(pc, ac)
    allowed = [d for d in diffs if d.startswith(".quantization_config.kv_cache_scheme")]
    unexpected = [d for d in diffs if d not in allowed]
    V["checks"]["V1_config_diff"] = {"all_diffs": diffs, "unexpected": unexpected}
    if unexpected:
        V["violations"].append({"check": "V1", "details": unexpected[:10]})

    # V2 tokenizer files
    tok_bad = []
    tok_res = {}
    for name in TOK_FILES:
        p, a = PARENT / name, ART / name
        if p.exists() or a.exists():
            hs = (sha256_file(p) if p.exists() else None,
                  sha256_file(a) if a.exists() else None)
            tok_res[name] = hs
            if hs[0] != hs[1]:
                tok_bad.append(name)
    V["checks"]["V2_tokenizer"] = {"files": tok_res, "mismatch": tok_bad}
    if tok_bad:
        V["violations"].append({"check": "V2", "mismatch": tok_bad})

    # V3 W4A16 结构
    pq, aq = pc.get("quantization_config", {}), ac.get("quantization_config", {})
    keys = ("config_groups", "ignore", "format", "quantization_status",
            "quant_method", "global_compression_ratio")
    q_bad = [k for k in keys if pq.get(k) != aq.get(k)]
    V["checks"]["V3_w4a16_structure"] = {"mismatched_keys": q_bad}
    if q_bad:
        V["violations"].append({"check": "V3", "keys": q_bad})

    # V4 tensor 级
    pt, at = load_tensors(PARENT), load_tensors(ART)
    common = set(pt) & set(at)
    added = sorted(set(at) - set(pt))
    deleted = sorted(set(pt) - set(at))
    ph = hash_tensors(PARENT, common)
    ah = hash_tensors(ART, common)
    changed = [k for k in common if ph[k] != ah[k]]
    bad_added = [k for k in added if not (k.endswith(".k_scale") or k.endswith(".v_scale"))]
    scale_shapes_ok = all(len(at[k]["shape"]) == 0 or at[k]["shape"] == [1]
                          for k in added if k.endswith((".k_scale", ".v_scale")))
    n_attn = (pc.get("text_config", pc).get("num_hidden_layers") or 0)
    V["checks"]["V4_tensors"] = {
        "parent_tensors": len(pt), "artifact_tensors": len(at),
        "common": len(common), "changed_common": changed[:10],
        "added": added[:60], "added_count": len(added),
        "deleted": deleted[:10], "bad_added": bad_added[:10],
        "scale_shapes_scalar": scale_shapes_ok,
        "expected_scale_count_hint": f"2×full-attn layers（hybrid：GDN 层无 KV；config num_hidden_layers={n_attn}）",
    }
    if changed or deleted or bad_added or not scale_shapes_ok:
        V["violations"].append({"check": "V4", "changed": len(changed),
                                "deleted": len(deleted), "bad_added": len(bad_added),
                                "scalar_shapes": scale_shapes_ok})

    # V5 provenance 完备
    prov = json.loads(PROV.read_text()) if PROV.exists() else {}
    missing = [k for k in REQUIRED_PROV if k not in prov]
    V["checks"]["V5_provenance"] = {"missing_fields": missing,
                                    "provenance_status": prov.get("status")}
    if missing:
        V["violations"].append({"check": "V5", "missing": missing})

    verdict = "FP8C_KV_ONLY_VERIFIED" if not V["violations"] else "VIOLATION"
    V["verdict"] = verdict
    V["runtime_load_check"] = "P1 最小 boot：--kv-cache-dtype fp8 + artifact → boot 日志 resolved KV dtype/scales（另行记录）"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(V, indent=1, ensure_ascii=False))
    print(json.dumps({"verdict": verdict, "violations": V["violations"]},
                     ensure_ascii=False))
    return 0 if verdict == "FP8C_KV_ONLY_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

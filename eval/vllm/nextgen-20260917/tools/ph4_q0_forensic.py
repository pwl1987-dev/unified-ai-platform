#!/usr/bin/env python3
"""Phase 04 P0A.2 — Q0 forensic（身份/血缘/模块 dtype/历史链取证）。

产出 repro/quant-phase04/q0-forensic.json：
  1. 全文件 SHA manifest（Q0 目录 21G，逐文件 sha256）
  2. config/tokenizer SHA + 结构指纹（vs teacher merged-bf16）
  3. module dtype map（从 quantization_config 展开三组 targets → 模块族精度表）
  4. parent lineage（merge_meta + TRAIN-NOTES 事件链 + 结构比对结论）
  5. quant_*.py 历史链（inference/vllm/prepare/ 脚本 SHA 清单）
  6. recipe 缺失如实记录（AutoRound 原始 recipe 不在盘——仅 TRAIN-NOTES 文字记录）
权重级 spot 抽查（--spot-check，在 fp8c-build 容器 venv 或含 compressed_tensors 的
解释器内运行）：抽 3 个 Linear 张量 dequant vs teacher bf16 原值 → cosine。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

Q0 = "/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128"
TEACHER = "/data/compose/qwen27b/train/merged-bf16"
NG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(NG, "repro", "quant-phase04")
OUT = os.path.join(OUT_DIR, "q0-forensic.json")
PREP = os.path.join(os.path.dirname(NG), "..", "inference", "vllm", "prepare")
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                   "chat_template.jinja", "preprocessor_config.json")


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def spot_check() -> list:
    """权重级血缘抽查：Q0 pack-quantized decompress vs teacher bf16 原值 cosine。

    compressed_tensors 0.18：PackedQuantizationCompressor.decompress(state_dict, scheme)
    ——state_dict 用模块局部名（weight_packed/weight_scale/weight_zero_point）。
    """
    import torch
    from safetensors import safe_open
    from compressed_tensors import PackedQuantizationCompressor
    from compressed_tensors.quantization import QuantizationArgs, QuantizationScheme

    idx = json.load(open(os.path.join(Q0, "model.safetensors.index.json")))
    weight_map = idx["weight_map"]
    cand = sorted(weight_map.keys())
    picks = [k for k in cand if k.endswith("q_proj.weight_packed")][:1] \
          + [k for k in cand if "in_proj" in k and k.endswith(".weight_packed")][:1] \
          + [k for k in cand if k.endswith("down_proj.weight_packed")][:1]
    scheme = QuantizationScheme(
        targets=["Linear"],
        weights=QuantizationArgs(num_bits=4, group_size=128, strategy="group",
                                 symmetric=True))
    out = []
    for packed_name in picks:
        base = packed_name[: -len(".weight_packed")]
        local = {}
        shard_of = {}
        for suffix in ("weight_packed", "weight_scale", "weight_zero_point",
                       "weight_shape"):
            full = f"{base}.{suffix}"
            if full in weight_map:
                shard_of[suffix] = os.path.join(Q0, weight_map[full])
        for suffix, shard in shard_of.items():
            with safe_open(shard, framework="pt") as f:
                local[suffix] = f.get_tensor(f"{base}.{suffix}")
        dec = PackedQuantizationCompressor.decompress(local, scheme)
        deq = dec["weight"].to(torch.float32)
        tidx = json.load(open(os.path.join(TEACHER, "model.safetensors.index.json")))["weight_map"]
        ref_name = f"{base}.weight"
        with safe_open(os.path.join(TEACHER, tidx[ref_name]), framework="pt") as ft:
            ref = ft.get_tensor(ref_name).to(torch.float32)
        cos = torch.nn.functional.cosine_similarity(deq.flatten(), ref.flatten(), dim=0).item()
        rel = (deq - ref).norm().item() / ref.norm().item()
        out.append({"tensor": base, "shape": list(ref.shape),
                    "cosine": round(cos, 6), "relative_frobenius": round(rel, 6)})
    return out


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    rep: dict = {"purpose": "Phase 04 P0A.2 Q0 forensic", "taken_utc":
                 __import__("datetime").datetime.now().astimezone().isoformat(),
                 "q0_dir": Q0}

    # 1) 全文件 SHA
    files = {}
    for f in sorted(os.listdir(Q0)):
        p = os.path.join(Q0, f)
        if os.path.isfile(p):
            files[f] = {"sha256": sha256_file(p), "bytes": os.path.getsize(p)}
    rep["artifact_files"] = files

    # 2) teacher 结构指纹（复检，血缘判定已在 P0A.3 完成——此处固化进 forensic）
    tok_cmp = {}
    for f in TOKENIZER_FILES:
        a, b = os.path.join(TEACHER, f), os.path.join(Q0, f)
        if os.path.exists(a) and os.path.exists(b):
            tok_cmp[f] = "MATCH" if sha256_file(a) == sha256_file(b) else "DIFF"
    m_cfg = json.load(open(os.path.join(TEACHER, "config.json")))
    q_cfg = json.load(open(os.path.join(Q0, "config.json")))
    nonquant_equal = {k: v for k, v in m_cfg.items() if k != "quantization_config"} == \
                     {k: v for k, v in q_cfg.items() if k != "quantization_config"}
    rep["teacher_lineage"] = {
        "verdict": "VERIFIED_LINEAGE",
        "teacher_dir": TEACHER,
        "merge_meta": json.load(open(os.path.join(TEACHER, "merge_meta.json"))),
        "evidence": {
            "tokenizer_files": tok_cmp,
            "config_non_quant_fields_equal": nonquant_equal,
            "chain": "Qwen3.8-27B-BF16 + coding-LoRA(checkpoint-4840) --PEFT merge_and_unload--> "
                     "merged-bf16(52G/12shards) --AutoRound 0.15 W4A16 sym g128 "
                     "(calib-v11-autoround.jsonl 1074 样本, TRAIN-NOTES 2026-09-06 S1)--> "
                     "Q0 --quant_lm_head.py/quant_embed.py 就地 int8 头/embed--> 现役形态",
            "notes": "52G 底座 Qwen3.8-27B-BF16 = merge 的 base（粗辈）；sensitivity teacher "
                     "必须用 merged-bf16（精确 parent），不用底座",
        },
    }

    # 3) module dtype map（从 quantization_config 展开）
    qc = q_cfg.get("quantization_config", {})
    dmap = {"groups": {}, "ignore_count": len(qc.get("ignore", [])),
            "ignore_summary": {"vision": 0, "gdn_in_proj": 0, "lm_head": 0, "other": []}}
    for gname, g in (qc.get("config_groups") or {}).items():
        w = (g or {}).get("weights") or {}
        dmap["groups"][gname] = {
            "targets": g.get("targets"),
            "weights_bits": w.get("num_bits"), "group_size": w.get("group_size"),
            "strategy": w.get("strategy"), "symmetric": w.get("symmetric"),
        }
    for it in qc.get("ignore", []):
        if "visual" in it:
            dmap["ignore_summary"]["vision"] += 1
        elif "in_proj" in it:
            dmap["ignore_summary"]["gdn_in_proj"] += 1
        elif "lm_head" in it:
            dmap["ignore_summary"]["lm_head"] += 1
        else:
            dmap["ignore_summary"]["other"].append(it)
    rep["module_dtype_map"] = dmap
    rep["module_dtype_plain"] = (
        "Linear=INT4 g128 sym（W4A16，memoryless_minmax）｜lm_head=INT8 g128（就地 requant）｜"
        "embed_tokens=INT8 g128（就地 requant）｜vision tower=BF16（ignore）｜"
        "GDN in_proj_a/b=BF16（ignore）｜mamba/recurrent state=不属权重量化轴")

    # 4) quant_*.py 历史链
    prep_dir = os.path.abspath(os.path.join(NG, "..", "..", "inference", "vllm", "prepare"))
    chain = {}
    if os.path.isdir(prep_dir):
        for f in sorted(os.listdir(prep_dir)):
            if f.endswith(".py"):
                chain[f] = sha256_file(os.path.join(prep_dir, f))
    rep["quant_script_chain"] = {"dir": prep_dir, "scripts_sha256": chain}

    # 5) recipe 缺失如实记录
    rep["recipe_gap"] = {
        "status": "MISSING_ON_DISK",
        "what_exists": "TRAIN-NOTES 2026-09-06 S1 文字记录（AutoRound 0.15 + 照抄 Huihui 配方 + "
                       "fp_layers=visual+linear_attn.norm+in_proj_a+in_proj_b+lm_head + "
                       "calib-v11-autoround.jsonl 1074 样本 + seqlen 1024 + 4 轮迭代坑记录）",
        "what_missing": "AutoRound 原始 recipe 脚本/参数对象/hyperparams 未随 artifact 落盘",
        "policy": "不补造历史 recipe；Q1/Q2/W8A16 等新 artifact 必须按 Phase 04 provenance "
                  "schema 全量落盘（gates-phase04）",
    }

    if "--spot-check" in sys.argv:
        rep["weight_level_spot_check"] = spot_check()

    json.dump(rep, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"[q0-forensic] {len(files)} files hashed -> {OUT}")
    if "weight_level_spot_check" in rep:
        print(json.dumps(rep["weight_level_spot_check"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

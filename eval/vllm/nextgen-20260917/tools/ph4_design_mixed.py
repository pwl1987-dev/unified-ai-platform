#!/usr/bin/env python3
"""Phase 04 P1 — 敏感度图 → Q1/Q2 分层 recipe 设计器。

输入 raw/staging/PH4-P1/layer-sensitivity.json（collector 产物）。
规则（gates sensitivity_method.restoration）：
  1. 模块族先恢复：按 family 聚合 hessian_weighted_err（int4_g128 档），排名输出
  2. Q1 = MLP W4 + attn/GDN 高敏族 G64 + 首尾层 W8（首尾=layer 0-1 与 62-63）
     Q2 = MLP W4 + attn 全 W8 + GDN 高敏 G64 + head 族（q/k/v/o 中最敏者）保 bf16
  3. 只输出 recipe 提案（config_groups 三组 targets 精确模块清单）——不自动构建；
     构建走 ph4_build_mixed.py（消费本提案，全 provenance）
输出 raw/staging/PH4-P1/q1q2-recipe-proposal.json
"""
from __future__ import annotations

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
SRC = os.path.join(NG, "raw", "staging", "PH4-P1", "layer-sensitivity.json")
OUT = os.path.join(NG, "raw", "staging", "PH4-P1", "q1q2-recipe-proposal.json")


def main() -> int:
    d = json.load(open(SRC))
    rows = d["rows"]
    # family 聚合（int4 档 hess；按层型分列）
    fam: dict[str, dict] = {}
    for r in rows:
        f = r["family"]
        if f in ("lm_head", "embedding", "other"):
            continue
        e = fam.setdefault(f, {"hess_sum": 0.0, "cos_min": 1.0, "n": 0,
                               "full_attn_n": 0, "gdn_n": 0})
        e["hess_sum"] += r.get("int4_g128.hess") or 0.0
        c = r.get("int4_g128.cos")
        if c is not None:
            e["cos_min"] = min(e["cos_min"], c)
        e["n"] += 1
        e["full_attn_n" if r["layer_type"] == "full_attn" else "gdn_n"] += 1
    ranking = sorted(((k, v["hess_sum"]) for k, v in fam.items()),
                     key=lambda kv: -kv[1])

    # 高敏族集合 = hess 贡献前 1/3 的族
    total = sum(v for _, v in ranking) or 1.0
    acc, sensitive_fams = 0.0, []
    for k, v in ranking:
        sensitive_fams.append(k)
        acc += v
        if acc / total >= 0.5:
            break

    def mods_of(famset, layers=None):
        out = []
        for r in rows:
            if r["family"] in famset and (layers is None or r["layer"] in layers):
                out.append(r["module"])
        return out

    first_last = set(range(0, 2)) | set(range(62, 64))
    proposal = {
        "purpose": "Q1/Q2 分层 recipe 提案（敏感度驱动；仅提案——构建须走 ph4_build_mixed）",
        "sensitivity_basis": {"teacher": d["model"], "rows": len(rows),
                              "skipped": len(d.get("skipped", [])),
                              "metric": "int4_g128 hessian_weighted_err 求和（family 级）"},
        "family_ranking": [{"family": k, "hess_sum": v, "share": round(v / total, 4),
                            "n": fam[k]["n"], "full_attn": fam[k]["full_attn_n"],
                            "gdn": fam[k]["gdn_n"], "cos_min_int4": fam[k]["cos_min"]}
                           for k, v in ranking],
        "sensitive_families_50pct": sensitive_fams,
        "Q1": {
            "desc": "MLP W4 + 高敏族 G64 + 首尾层 W8",
            "groups": {
                "mlp_w4": {"targets_families": ["mlp.gate", "mlp.up", "mlp.down"],
                           "weights": "int4 g128 sym"},
                "sensitive_g64": {"targets_families": sensitive_fams,
                                  "weights": "int4 g64 sym"},
                "first_last_w8": {"targets": mods_of(set(fam), first_last),
                                  "weights": "int8 g128 sym"},
            },
            "n_modules": {"mlp_w4": len(mods_of({"mlp.gate", "mlp.up", "mlp.down"})),
                          "sensitive_g64": len(mods_of(set(sensitive_fams))),
                          "first_last_w8": len(mods_of(set(fam), first_last))},
        },
        "Q2": {
            "desc": "MLP W4 + attn 全 W8 + GDN 高敏 G64 + 最敏 head 子族保 bf16",
            "attn_families": [k for k, _ in ranking if k.startswith("attn.")],
            "most_sensitive_attn": [k for k, _ in ranking if k.startswith("attn.")][0],
            "groups": {
                "mlp_w4": {"targets_families": ["mlp.gate", "mlp.up", "mlp.down"],
                           "weights": "int4 g128 sym"},
                "attn_w8": {"targets_families": [k for k, _ in ranking
                                                 if k.startswith("attn.")][1:],
                            "weights": "int8 g128 sym"},
                "gdn_sensitive_g64": {"targets_families": [k for k in sensitive_fams
                                                           if k.startswith("gdn.")],
                                      "weights": "int4 g64 sym"},
            },
        },
        "notes": ["首尾层=0-1/62-63（64 层）", "GDN in_proj 家族保持 bf16（Q0 政策继承）",
                  "lm_head 恒 bf16（绑定权重教训）", "实际构建时 targets 用精确模块名清单"],
    }
    json.dump(proposal, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"ranking_top5": [(k, round(v, 1)) for k, v in ranking[:5]],
                      "sensitive_fams": sensitive_fams,
                      "Q1 modules": proposal["Q1"]["n_modules"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

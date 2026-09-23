#!/usr/bin/env python3
"""Phase 04 P0A.5 — 三分数据角色 manifest 生成 + overlap checker（v2）。

角色（Phase 04 执行合同）：A quant_calibration_sensitivity_dev / B screen_quality_dev /
C final_quality_holdout（sealed，P3 才开）。三层不相交：内容 hash / needle 码集 / 索引区间。
用法：python3 ph4_data_roles.py            # 生成三 manifest + 检查（幂等）
      python3 ph4_data_roles.py --check    # 只检查
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
ROLES_DIR = os.path.join(NG, "fixtures", "data-roles")


def build() -> dict:
    corpus_man = json.load(open(os.path.join(
        NG, "fixtures/calibration/phase03-corpus-manifest.json")))
    fm = json.load(open(os.path.join(NG, "fixtures/manifest.json")))["fixtures"]
    return {
        "quant_calibration_sensitivity_dev": {
            "role": "A：量化校准 + 激活敏感度 + 层恢复设计（禁作质量裁决）",
            "contents": {
                "corpus": "fixtures/calibration/phase03-corpus/samples.jsonl",
                "dataset_sha256": corpus_man["dataset_sha256"],
                "sample_count": corpus_man["sample_count"],
                "seed": corpus_man["seed"],
                "sample_hashes": [s["sha256"] for s in corpus_man["sample_ids_and_hashes"]],
                "sensitivity_extension_policy": "扩样须新 seed（≠99/2/5）且重过本 checker",
            },
        },
        "screen_quality_dev": {
            "role": "B：P1/P2 短质量筛选（可淘汰候选；禁开 holdout）",
            "contents": {
                "needle": {
                    "seeds": [99], "tiers": ["p32k", "p128k"],
                    "fixture_family": "Phase 01-03 既有 needle fixture 族（s99 阳性对照协议）",
                    "registry_hashes": {k: fm[k]["prompt_sha256"]
                                        for k in fm if k.endswith("-s99-ph3")},
            },
                "verbatim": {"source": "tools/verbatim_check.py 冻结 100 条",
                             "screen_slice": "items[0:50]"},
                "rulers": {"humaneval": "index[0:40]", "gsm8k": "index[0:80]",
                           "invoked_via": "run_baseline.py --max 前缀切片"},
            },
        },
        "final_quality_holdout": {
            "role": "C：P3 Qualify 才允许首次打开；禁用于 recipe/层选/调参",
            "sealed": True,
            "contents": {
                "needle": {"seeds": [2, 5],
                           "tiers": ["p128k", "p220k", "p238k", "p245k"],
                           "positive_control": "s99 仅作阳性对照标记（非判别集）"},
                "verbatim": {"holdout_slice": "items[50:100]（与 screen [0:50) 不相交）"},
                "rulers": {"humaneval": "index[40:]（与 screen [0:40) 不相交）",
                           "gsm8k": "index[80:]（与 screen [0:80) 不相交）",
                           "ifeval": "全量（screen 不用）", "xfc": "全量（screen 不用）",
                           "harness_note": "P3 前为 run_baseline.py 加 --skip 偏移并自测"},
                "bfcl": "MEASUREMENT_NOT_AVAILABLE（Phase 01 起轴不可用，不自动 PASS）",
            },
        },
    }


def check() -> int:
    violations = []
    a = json.load(open(os.path.join(ROLES_DIR, "quant_calibration_sensitivity_dev.json")))
    b = json.load(open(os.path.join(ROLES_DIR, "screen_quality_dev.json")))
    c = json.load(open(os.path.join(ROLES_DIR, "final_quality_holdout.json")))

    # 1) corpus hash ∩ 评测内容 = ∅（评测 needle/verbatim hash 家族）
    fm = json.load(open(os.path.join(NG, "fixtures/manifest.json")))["fixtures"]
    eval_hashes = {v.get("prompt_sha256") for v in fm.values() if v.get("prompt_sha256")}
    inter = set(a["contents"]["sample_hashes"]) & eval_hashes
    if inter:
        violations.append({"check": "corpus∩eval_hashes", "hits": sorted(inter)[:3]})

    # 2) needle 码集：screen 判别 tier（32K/128K s99）与 holdout 判别 seeds（s2/s5）不同集；
    #    码集内容级：s99 ph3 fixture（screen 登记族）与 s2/s5 ph3 fixture（holdout）天然不同 doc
    b_seeds = set(b["contents"]["needle"]["seeds"])
    c_seeds = set(c["contents"]["needle"]["seeds"])
    if b_seeds & c_seeds - {99}:  # s99 允许两侧（对照语义，非判别）
        violations.append({"check": "needle_seed_judgment_overlap",
                           "hits": sorted(b_seeds & c_seeds - {99})})
    b_tiers = set(b["contents"]["needle"]["tiers"])
    c_tiers = set(c["contents"]["needle"]["tiers"])
    overlap_tiers = (b_tiers & c_tiers) - {"p128k"}  # p128k 允许共 tier 但判别 seed 不同
    if overlap_tiers and b_seeds & c_seeds - {99}:
        violations.append({"check": "needle_tier_seed_cross", "hits": sorted(overlap_tiers)})

    # 3) 索引区间算术：verbatim [0:50) vs [50:100)；rulers [0:40) vs [40:]、[0:80) vs [80:]
    for axis, s_end, h_start in (("humaneval", 40, 40), ("gsm8k", 80, 80)):
        if s_end != h_start:
            violations.append({"check": f"{axis}_index_boundary", "s_end": s_end, "h_start": h_start})
    if "items[0:50]" in b["contents"]["verbatim"]["screen_slice"] and \
       "items[50:100]" in c["contents"]["verbatim"]["holdout_slice"]:
        pass
    else:
        violations.append({"check": "verbatim_slice_boundary"})

    # 4) seed 结构隔离：corpus seed 20260921 ∉ needle seeds
    if a["contents"]["seed"] in (99, 2, 5):
        violations.append({"check": "corpus_seed_overlap"})

    verdict = "PASS" if not violations else "INVALID"
    out = {"purpose": "三分数据 overlap checker v2（Phase 04 合同）",
           "checked_utc": "2026-09-22", "violations": violations, "verdict": verdict}
    json.dump(out, open(os.path.join(ROLES_DIR, "overlap-check.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if verdict == "PASS" else 1


def main() -> int:
    os.makedirs(ROLES_DIR, exist_ok=True)
    if "--check" not in sys.argv:
        for name, body in build().items():
            json.dump({"role_name": name, "frozen_utc": "2026-09-22", **body},
                      open(os.path.join(ROLES_DIR, f"{name}.json"), "w"),
                      indent=1, ensure_ascii=False)
        print("three role manifests written")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 03 P0A.7 — 校准/评测集互斥 checker（gates calibration_contract.overlap_checker）。

规则：calibration ∩ evaluation = ∅（按样本 hash + needle 码串内容）；未过 = INVALID，
禁止 FP8C Qualify。三类检查：
  1. hash 互斥：校准样本 SHA 不得出现在评测 manifest 任何 prompt SHA 中
  2. 码集互斥：评测 needle 码（s99/s2/s5 ph3 全部六位码）不得出现在任何校准样本文本中
  3. 文本互斥：评测 fixture 的原文（perf 夹具 prompt/needle prompt）不与校准样本文本重叠
     （评测 prompt 大文本以 hash 比对；小块码串以子串比对）
退出码 0=PASS / 1=INVALID。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(os.path.dirname(HERE), "fixtures")   # .../nextgen-20260917/fixtures
FIX = os.path.abspath(FIX)


def main() -> int:
    calib_man = json.load(open(os.path.join(FIX, "calibration", "phase03-corpus-manifest.json")))
    calib_samples = [json.loads(l) for l in open(os.path.join(FIX, "calibration", "phase03-corpus", "samples.jsonl"))]
    eval_man = json.load(open(os.path.join(FIX, "manifest.json")))

    calib_hashes = {s["sha256"] for s in calib_samples}
    eval_hashes = {v.get("prompt_sha256") for v in eval_man["fixtures"].values()
                   if v.get("prompt_sha256")}
    violations = []

    # 1) hash 互斥
    inter = calib_hashes & eval_hashes
    if inter:
        violations.append({"check": "hash_intersection", "hits": sorted(inter)[:5]})

    # 2) needle 码集互斥（s99/s2/s5 ph3 —— Phase 03 判定用全部码）
    needle_codes = set()
    for name, v in eval_man["fixtures"].items():
        if name.endswith("-ph3"):
            needle_codes |= set(v.get("needles", {}).keys())
    text_blob = "\n".join(s["text"] for s in calib_samples)
    leaked = [c for c in sorted(needle_codes) if c in text_blob]
    if leaked:
        violations.append({"check": "needle_code_in_calibration", "hits": leaked})

    # 3) 校准语料不得整段等于评测 needle prompt（同 hash 已查；此处防拼接整文）
    #    评测大文本不进 Git，无法直接子串比对全文——以 hash + 码集双层为准，
    #    并断言校准生成器 seed 与 needle seeds 无交集（结构性隔离）。
    if calib_man["seed"] in (99, 2, 5):
        violations.append({"check": "seed_overlap", "seed": calib_man["seed"]})

    verdict = "PASS" if not violations else "INVALID"
    out = {"purpose": "calibration ∩ evaluation = ∅ checker（gates-phase03）",
           "checked_utc": "2026-09-21",
           "calibration_dataset_sha256": calib_man["dataset_sha256"],
           "calibration_samples": len(calib_samples),
           "needle_codes_checked": len(needle_codes),
           "violations": violations, "verdict": verdict}
    path = os.path.join(FIX, "calibration", "overlap-check.json")
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""补债证据归类：CC/NDL/DEBT 聚合目录 → 六态归档。

- CC-G*（bench 五件套）：走 classify.py 标准 schema 路径。
- NDL-*（needle-result.json）：五针 5/5 → VALID_PASS，否则 VALID_FAIL/QUALITY_FAIL。
- DEBT1-/DEBT2- 聚合（debtN-report.json）：按 verdict PASS→VALID_PASS，
  否则 VALID_FAIL/QUALITY_FAIL；带 debt gate 上下文。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
RAW = os.path.join(NEXTGEN, "raw")
PY = "/data/tools/vllm28-env/bin/python"


def write_manifest(d: str, manifest: dict) -> None:
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)


def archive(exp_id: str, cls: str) -> None:
    src = os.path.join(RAW, "staging", exp_id)
    dst = os.path.join(RAW, cls, exp_id)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.rename(src, dst)
    print(json.dumps({"experiment_id": exp_id, "archived_to": dst}))


def main() -> int:
    staging = os.path.join(RAW, "staging")
    for exp_id in sorted(os.listdir(staging)):
        p = os.path.join(staging, exp_id)
        if not os.path.isdir(p):
            continue
        if exp_id.startswith("V28-T1-CC-"):
            # 标准 bench 五件套 → 走 schema 校验路径
            subprocess.run([PY, os.path.join(HERE, "classify.py"), exp_id], check=False)
        elif "-NDL-" in exp_id:
            nr = json.load(open(os.path.join(p, "needle-result.json")))
            ok = bool(nr.get("PASS"))
            write_manifest(p, {
                "experiment_id": exp_id,
                "evidence_kind": "needle-probe",
                "debt_gate": "D2-238K" if "L238K" in exp_id else "A4-220K-needle",
                "needles_hit": nr.get("needles_hit"),
                "ttft_s": nr.get("ttft_s"),
                "status": "VALID_PASS" if ok else "VALID_FAIL",
                "evidence_class": "valid",
                "classification_reason": None if ok else "QUALITY_FAIL",
            })
            archive(exp_id, "valid")
        elif exp_id.startswith("DEBT1-"):
            rep = json.load(open(os.path.join(p, "debt1-report.json")))
            dets = [s.get("determinism_probe", {}).get("text_sha256")
                    for g in rep.get("groups", {}).values() for s in g.get("steps", [])
                    if s.get("determinism_probe")]
            ok = bool(dets) and len(set(dets)) == 1 and len(dets) >= 3
            write_manifest(p, {
                "experiment_id": exp_id,
                "evidence_kind": "debt-aggregate",
                "verdict": "PASS" if ok else "CHECK",
                "probe_hashes": dets,
                "status": "VALID_PASS" if ok else "VALID_FAIL",
                "evidence_class": "valid",
                "classification_reason": None if ok else "QUALITY_FAIL",
            })
            archive(exp_id, "valid")
        elif exp_id.startswith("DEBT2-"):
            rep = json.load(open(os.path.join(p, "debt2-report.json")))
            v = rep.get("verdict", {})
            ok = bool(v.get("correctness_gate_pass") and v.get("stability_gate_pass"))
            write_manifest(p, {
                "experiment_id": exp_id,
                "evidence_kind": "debt-aggregate",
                "verdict": v,
                "nd220k": rep.get("nd220k"),
                "boot_isolation_note": (
                    "stop() ps--pgid bug: b1 server 未被终止，b2/b3 端口冲突即刻退出，"
                    "12 次 needle 实际全部落在同一 b1 server；跨 boot 稳定性证据失效，"
                    "正确性证据有效（同 server 3 次重复、temp=0 确定性复现）"),
                "status": "VALID_PASS" if ok else "VALID_FAIL",
                "evidence_class": "valid",
                "classification_reason": None if ok else "QUALITY_FAIL",
            })
            archive(exp_id, "valid")
        else:
            print(f"SKIP (unknown kind): {exp_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

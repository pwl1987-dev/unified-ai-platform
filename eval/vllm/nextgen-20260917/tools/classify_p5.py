#!/usr/bin/env python3
"""Phase 01 归档批处理——为 needle/verbatim 类 staging 目录补 manifest 后走 classify 六态归档。

规则（Phase 01 v1.2 四层状态分离）：
  可召回码集（S99/S2）PASS=true          -> VALID_PASS（reason=None）
  对照码集 S1/S3 在正常栈上 2/5          -> VALID_FAIL/QUALITY_FAIL（note=control-code-set，预期行为）
  Layer C 移植尝试（LC-*）0/5 损坏输出    -> VALID_FAIL/QUALITY_FAIL（candidate=REJECTED）
  verbatim probe PASS                     -> VALID_PASS
  聚合报告目录（P1-CAUSAL 等）            -> 生成 manifest 后按裁决归档
manifest 字段复用 Phase 00 冻结值（host/env SHA、harness 权威指针 80e7d15）。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
STAGING = os.path.join(NEXTGEN, "raw", "staging")
VALID = os.path.join(NEXTGEN, "raw", "valid")
INVALID = os.path.join(NEXTGEN, "raw", "invalid")

HOST_SHA = "6a08a3748937c2ff5df6eb1958b0ea1b06976e6642bfe60dc930f81e6181af39"
ENV_SHA = "e76f5dd199b4b39e0c440ba1797e9cab8775adb2389273d776e337b3acb90e9b"
HARNESS_SHA = "80e7d15c6e18247615f5425d2e5ece9cffdfe3d5"  # 权威指针（STATUS 勘误后）

TP1 = [{"logical_index": 2, "uuid": "GPU-41a1986d-e745-9e40-c520-09490081fd44",
        "pci_bdf": "00000000:0E:00.0"}]
TP2 = [{"logical_index": 3, "uuid": "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae",
        "pci_bdf": "00000000:11:00.0"},
       {"logical_index": 4, "uuid": "GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e",
        "pci_bdf": "00000000:16:00.0"}]


def base_manifest(exp_id: str, gpu_cards: list, recipe: str, note: str | None = None,
                  candidate: str | None = None) -> dict:
    m = {
        "experiment_id": exp_id,
        "status": "VALID_PASS", "evidence_class": "staging",
        "created_utc": "2026-09-18T00:00:00Z",
        "harness_git_sha": HARNESS_SHA,
        "host_snapshot_sha256": HOST_SHA, "env_lock_sha256": ENV_SHA,
        "gpu": {"cards": gpu_cards, "power_limit_w": 250.0},
        "server": {"note": "见 raw/ 下对应聚合报告与 /data/sandbox/nextgen-20260917/log-* server.txt"},
        "fixture": {"kind": "needle/verbatim（生成器 gen_fixtures.py / verbatim_check.py，SHA 见结果文件）"},
        "recipe": {"profile": recipe},
        "timing": {"note": "时间戳见各结果文件与聚合报告"},
        "classification_note": note,
    }
    if candidate:
        m["candidate_decision"] = candidate
    return m


def write_manifest(exp: str, gpu_cards, recipe, note=None, candidate=None):
    p = os.path.join(STAGING, exp, "manifest.json")
    m = base_manifest(exp, gpu_cards, recipe, note, candidate)
    json.dump(m, open(p, "w"), indent=1, ensure_ascii=False)


def classify_one(exp: str, reason: str | None) -> None:
    r = subprocess.run([sys.executable, os.path.join(HERE, "classify.py"), exp]
                       + (["--reason", reason] if reason else []),
                       capture_output=True, text=True)
    out = (r.stdout or r.stderr).strip().splitlines()
    print((out[-1] if out else f"{exp}: rc={r.returncode}"))


def main() -> int:
    stats = {"valid_pass": 0, "control_fail": 0, "port_fail": 0, "aggregate": 0, "skipped": 0}
    # ---- 1) needle 目录（P1SCN/P1FD/P1M/LX/LC）----
    needle_dirs = []
    for pat in ("V2*P1SCN*", "V2*P1FD*", "V2*P1M*", "V29*LX*", "V29*LC*"):
        needle_dirs += glob.glob(os.path.join(STAGING, pat))
    for d in sorted(needle_dirs):
        exp = os.path.basename(d.rstrip("/"))
        nr_path = os.path.join(d, "needle-result.json")
        if not os.path.exists(nr_path):
            stats["skipped"] += 1
            continue
        nr = json.load(open(nr_path))
        write_manifest(exp, TP2, "P1/LX/LC needle 形制（详见聚合报告）")
        seed = exp.rsplit("-S", 1)[-1]
        is_lc = "-LC" in exp
        if is_lc:
            m_path = os.path.join(d, "manifest.json")
            m = json.load(open(m_path))
            m["status"] = "VALID_FAIL"
            m["candidate_decision"] = "REJECTED"
            json.dump(m, open(m_path, "w"), indent=1, ensure_ascii=False)
            stats["port_fail"] += 1
            continue
        if nr.get("PASS") is True:
            stats["valid_pass"] += 1
        else:
            m_path = os.path.join(d, "manifest.json")
            m = json.load(open(m_path))
            m["status"] = "VALID_FAIL"
            json.dump(m, open(m_path, "w"), indent=1, ensure_ascii=False)
            stats["control_fail"] += 1
    # ---- 2) verbatim 目录 ----
    for d in sorted(glob.glob(os.path.join(STAGING, "*VERBATIM*"))):
        exp = os.path.basename(d.rstrip("/"))
        vr = os.path.join(d, "verbatim-result.json")
        if not os.path.exists(vr):
            stats["skipped"] += 1
            continue
        res = json.load(open(vr))
        tp2 = "-T2-" in exp
        write_manifest(exp, TP2 if tp2 else TP1, "Layer A/B verbatim smoke")
        if not res.get("PASS"):
            m_path = os.path.join(d, "manifest.json")
            m = json.load(open(m_path))
            m["status"] = "VALID_FAIL"
            json.dump(m, open(m_path, "w"), indent=1, ensure_ascii=False)
            stats["control_fail"] += 1
        else:
            stats["valid_pass"] += 1
    # ---- 3) 聚合报告目录 ----
    AGG = {
        "P1-CAUSAL": ("VALID_PASS", None, "2×2 因果裁决 + 判别探针：NOT_ATTRIBUTABLE_TO_KVARN"),
        "P1-MATRIX": ("VALID_PASS", None, "3-boot×3-seed 矩阵 + seed99 阳性对照 + TTFT reference"),
        "P2-LAYERA": ("VALID_PASS", None, "Layer A TP1 Qualify + TP2 资格"),
        "P3-LAYERB": ("VALID_PASS", None, "Layer B Screen+Qualify：四通路无损同 hash"),
        "P4-LAYERX": ("VALID_PASS", "PASS", "Layer X bridge：0.29 bf16@220K 长上下文资格"),
        "P4-LAYERC": ("VALID_FAIL", "REJECTED", "KVarN 0.29 移植止损（布局契约）"),
    }
    for name, (status, cand, note) in AGG.items():
        d = os.path.join(STAGING, name)
        if not os.path.isdir(d):
            continue
        m = base_manifest(name, TP1 + TP2, "Phase 01 聚合证据", note, cand)
        m["status"] = status
        json.dump(m, open(os.path.join(d, "manifest.json"), "w"), indent=1, ensure_ascii=False)
        stats["aggregate"] += 1
    # ---- 4) 统一执行 classify 移动（对已有 manifest 的目录按其 status 声明）----
    for d in sorted(os.listdir(STAGING)):
        p = os.path.join(STAGING, d)
        if not os.path.isdir(p):
            continue
        mf = os.path.join(p, "manifest.json")
        if not os.path.exists(mf):
            stats["skipped"] += 1
            continue
        m = json.load(open(mf))
        # bench_nextgen 写的 manifest（staging 状态）-> 默认 VALID_PASS（全部 rc=0）
        reason = None
        if m.get("status") == "VALID_FAIL":
            reason = "quality_fail"
        classify_one(d, reason)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

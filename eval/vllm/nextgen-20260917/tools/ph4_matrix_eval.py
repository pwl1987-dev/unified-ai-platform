#!/usr/bin/env python3
"""Phase 04 P2 — 矩阵六轴汇总（消费 V29-T2-PH4-* run 目录 → ph4-matrix-summary.json）。

六轴：quality(needle/verbatim/micro) / C1 / C4 / prefill(TTFT) / VRAM / energy(J-per-token)
+ artifact size + startup（各臂 boot 日志/探针 JSON 引用）。
比较规则：gates epsilon 带（throughput/prefill 3%、energy 5%、VRAM max(200MiB,2%)、quality pp）。
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
ST = os.path.join(NG, "raw", "staging")

ARMS = {
    "Q0": ("Q0", "V29-T2-PH4-Q0-", None, None),
    "W8": ("W8A16", "V29-T2-PH4-W8-", "V29-T2-PH4-W8S-", "128K=CAPACITY_LIMIT(boot OOM 17.4GiB/卡)"),
    "Q4C": ("Q4_CODING", "V29-T2-PH4-Q4C-", "V29-T2-PH4-Q4S-", "128K=CAPACITY_LIMIT(max_model_len 118784)"),
    "Q1M": ("Q1_MIXED", "V29-T2-PH4-Q1M-", None, None),
    "Q2M": ("Q2_MIXED", "V29-T2-PH4-Q2M-", None, None),
}
# 修复批前缀：Q0 的 128K 修复 = Q0T；W8/Q4C 短形制 = W8S/Q4S
FIX_PREFIX = {"Q0": ["V29-T2-PH4-Q0T-C1-L128K", "V29-T2-PH4-Q0T-C2-L128K"],
              "Q1M": ["V29-T2-PH4-Q1T-C1-L128K", "V29-T2-PH4-Q1T-C2-L128K"],
              "Q2M": ["V29-T2-PH4-Q2T-C1-L128K", "V29-T2-PH4-Q2T-C2-L128K"]}


def cell_metric(prefix, mode, field, aggregate=False):
    vals = []
    for d in sorted(glob.glob(os.path.join(ST, prefix + "*"))):
        mp = os.path.join(d, "metrics.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        if m.get("requests_ok", 0) < 1 or m.get("http_errors", 0) > 0:
            continue
        if aggregate:
            v = (m.get("aggregate") or {}).get("aggregate_output_tok_s")
            if isinstance(v, (int, float)):
                vals.append(float(v))
        else:
            for rq in m.get("per_request", []):
                if rq.get("ok") and isinstance(rq.get(field), (int, float)):
                    vals.append(float(rq[field]))
    if not vals:
        return None
    return {"n": len(vals), "median": round(statistics.median(vals), 3),
            "min": round(min(vals), 3), "max": round(max(vals), 3)}


def energy_of(prefix):
    out = []
    for d in sorted(glob.glob(os.path.join(ST, prefix + "*"))):
        ep = os.path.join(d, "energy.json")
        if os.path.exists(ep):
            e = json.load(open(ep))
            if e.get("J_per_output_token"):
                out.append(e["J_per_output_token"])
    if not out:
        return None
    return {"n": len(out), "median_J_per_tok": round(statistics.median(out), 3)}


def main() -> int:
    import subprocess
    # 1) 先批量生成 energy.json
    dirs = [d for d in glob.glob(os.path.join(ST, "V29-T2-PH4-*-R*"))
            if os.path.exists(os.path.join(d, "nvml-samples.jsonl"))]
    subprocess.run([sys.executable, os.path.join(HERE, "ph4_energy_report.py"), *dirs],
                   capture_output=True, text=True)

    summary = {}
    for arm, (name, prefix, short_prefix, cap_note) in ARMS.items():
        entry = {"profile": name, "capacity_note": cap_note}
        # W8/Q4C 只有短形制臂（128K=容量墙）→ 全轴用短前缀；其余用主前缀
        base = short_prefix if short_prefix else prefix
        # D565 C1（f512）
        entry["d565_c1_decode"] = cell_metric(base + "C1-L0565", "F512",
                                              "client_observed_decode_tok_s")
        # P4K
        entry["p4k_c1_decode"] = cell_metric(base + "C1-L004K", "NS",
                                             "client_observed_decode_tok_s")
        entry["p4k_c1_ttft"] = cell_metric(base + "C1-L004K", "NS", "ttft_s")
        entry["p4k_c4_agg"] = cell_metric(base + "C4-L004K", "NS", None, aggregate=True)
        # P32K
        entry["p32k_c1_decode"] = cell_metric(base + "C1-L032K", "NS",
                                              "client_observed_decode_tok_s")
        entry["p32k_c1_ttft"] = cell_metric(base + "C1-L032K", "NS", "ttft_s")
        entry["p32k_c4_agg"] = cell_metric(base + "C4-L032K", "NS", None, aggregate=True)
        # P128K（Q0/Q1M/Q2M 走修复批前缀；W8/Q4C CAPACITY_LIMIT）
        if arm in FIX_PREFIX:
            entry["p128k_c1_decode"] = cell_metric(FIX_PREFIX[arm][0], "NS",
                                                   "client_observed_decode_tok_s")
            entry["p128k_c1_ttft"] = cell_metric(FIX_PREFIX[arm][0], "NS", "ttft_s")
            entry["p128k_c2_agg"] = cell_metric(FIX_PREFIX[arm][1], "NS", None,
                                                aggregate=True)
        # 能效
        entry["energy_J_per_tok"] = {k: energy_of(p) for k, p in (
            ("d565", base + "C1-L0565"), ("p4k_c4", base + "C4-L004K"),
            ("p32k_c1", base + "C1-L032K"))}
        summary[arm] = entry

    out = os.path.join(ST, "PH4-P2", "ph4-matrix-summary.json")
    json.dump(summary, open(out, "w"), indent=1, ensure_ascii=False)
    for arm, e in summary.items():
        d565 = (e["d565_c1_decode"] or {}).get("median")
        p32k = (e["p32k_c1_decode"] or {}).get("median")
        p4k4 = (e["p4k_c4_agg"] or {}).get("median")
        jtok = ((e["energy_J_per_tok"].get("p4k_c4") or {}).get("median_J_per_tok"))
        print(f"{arm:5s} d565={d565} p4kC4agg={p4k4} p32kC1={p32k} J/tok(p4kC4)={jtok}")
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

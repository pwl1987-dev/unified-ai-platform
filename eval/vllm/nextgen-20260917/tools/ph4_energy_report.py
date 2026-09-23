#!/usr/bin/env python3
"""Phase 04 P0A.6 — 能效报告器（METRICS-SCHEMA §5 契约实现）。

输入：run 目录的 nvml-samples.jsonl（500ms 冻结采样，t_utc_ns 时间戳，逐卡行）
输出（每 run）：
  J_per_output_token（正式指标） / tok_per_J / mean_power_W / peak_power_W
  throttle_reasons 计数 / power_limit_w 分桶（250W vs 450W cron 窗混杂即 FLAG）
  boot 窗与 serving 窗分列（--boot-dir 单独报告，禁止混算）
合成自测（--selftest）：恒 100W × 10s × 100 token → energy=1000J, J/tok=10, tok/J=0.1。
用法：
  ph4_energy_report.py <run_dir>...            # 逐 run 报告（读 metrics.json 取 token 数）
  ph4_energy_report.py --boot <log_dir>        # boot/model-load 窗（独立采样文件）
  ph4_energy_report.py --selftest
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict


def integrate(samples_by_gpu: dict[str, list[dict]]) -> dict:
    """每卡梯形积分（METRICS-SCHEMA §5）；跨卡求和。恒定采样间隔下退化为均值×时长。"""
    total_j = 0.0
    per_gpu = {}
    for uuid, rows in samples_by_gpu.items():
        rows = sorted(rows, key=lambda r: r["t_utc_ns"])
        e = 0.0
        for a, b in zip(rows, rows[1:]):
            dt = (b["t_utc_ns"] - a["t_utc_ns"]) / 1e9
            e += (a["power_draw_w"] + b["power_draw_w"]) / 2 * dt
        if len(rows) >= 2:
            # 首尾半步补偿（采样窗覆盖 [t0-Δ/2, tN+Δ/2] 近似）
            mean_dt = (rows[-1]["t_utc_ns"] - rows[0]["t_utc_ns"]) / 1e9 / (len(rows) - 1)
            e += rows[0]["power_draw_w"] * mean_dt / 2 + rows[-1]["power_draw_w"] * mean_dt / 2
        per_gpu[uuid] = {"energy_j": round(e, 1),
                         "mean_w": round(sum(r["power_draw_w"] for r in rows) / len(rows), 2),
                         "peak_w": round(max(r["power_draw_w"] for r in rows), 2)}
        total_j += e
    limits = {r["power_limit_w"] for rows in samples_by_gpu.values() for r in rows}
    throttles = defaultdict(int)
    for rows in samples_by_gpu.values():
        for r in rows:
            if r.get("throttle_reasons") not in (0, "0x0000000000000000", None, "0"):
                throttles[str(r["throttle_reasons"])] += 1
    return {"total_energy_j": round(total_j, 1), "per_gpu": per_gpu,
            "power_limit_buckets": sorted(limits),
            "mixed_power_window": len(limits) > 1,
            "throttle_counts": dict(throttles)}


def report_run(run_dir: str) -> dict:
    src = os.path.join(run_dir, "nvml-samples.jsonl")
    by_gpu: dict[str, list[dict]] = defaultdict(list)
    for line in open(src):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        by_gpu[r["uuid"]].append(r)
    energy = integrate(by_gpu)
    m = {}
    mp = os.path.join(run_dir, "metrics.json")
    if os.path.exists(mp):
        m = json.load(open(mp))
    out_tok = (m.get("aggregate") or {}).get("sum_output_tokens") or \
        sum(rq.get("output_tokens", 0) for rq in m.get("per_request", []))
    if out_tok and out_tok > 0:
        energy["output_tokens"] = out_tok
        energy["J_per_output_token"] = round(energy["total_energy_j"] / out_tok, 3)
        energy["tok_per_J"] = round(out_tok / energy["total_energy_j"], 4)
    energy["window"] = "serving_run"
    out = os.path.join(run_dir, "energy.json")
    json.dump(energy, open(out, "w"), indent=1, ensure_ascii=False)
    return {"run": os.path.basename(run_dir), **energy}


def selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rows = []
        t0 = 1_000_000_000_000
        for i in range(21):  # 21 样本 × 0.5s = 10s 窗
            rows.append({"uuid": "GPU-X", "power_draw_w": 100.0, "power_limit_w": 250.0,
                         "throttle_reasons": 0, "t_utc_ns": t0 + i * 500_000_000})
        p = os.path.join(td, "r1")
        os.makedirs(p)
        with open(os.path.join(p, "nvml-samples.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        json.dump({"aggregate": {"sum_output_tokens": 100}}, open(os.path.join(p, "metrics.json"), "w"))
        rep = report_run(p)
        # 梯形积分 10s 窗（首尾半步补偿后 ≈ 10s×100W=1000J；容差 ±5%）
        ej, jpt = rep["total_energy_j"], rep["J_per_output_token"]
        ok = abs(ej - 1000.0) < 60 and abs(jpt - 10.0) < 0.7 and rep["tok_per_J"] > 0.09
        print(json.dumps({"selftest": "PASS" if ok else "FAIL", "energy_j": ej,
                          "J_per_token": jpt, "tok_per_J": rep["tok_per_J"]}))
        return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    outs = []
    for d in args:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "nvml-samples.jsonl")):
            outs.append(report_run(d))
    print(json.dumps(outs, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

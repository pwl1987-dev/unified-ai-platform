#!/usr/bin/env python3
"""p02_evaluate — Phase 02 Screen 判定评估器（sign-aware，消费 gates-phase02.yaml）。

用法:
  python3 p02_evaluate.py --gates repro/gates-phase02.yaml \
    --label NBT3072-vs-B0L32 --scalar \
    --ref <refRun1> <refRun2> <refRun3> --cand <candRun1> <candRun2> <candRun3> \
    --primary tpot_p50 goodput_rps --other ttft_p95 aggregate_tok_s \
    [--out staging/P02-SCREEN/<label>.json]

  python3 p02_evaluate.py --gates ... --label admission-L1 --policy \
    --ref ... --cand ... --primary ttft_p95 \
    --policy-json '{"overload_p95_protection": true, "rejection_predictability": true,
                    "served_goodput_regression_non_overload": 0.02, "regression_max": 0.05}'

指标提取（每 run 先算、跨 run 取中位，Phase 00 口径）：
  ttft_p50/p95/p99 | tpot_p50 | e2e_p50 | goodput_rps | aggregate_tok_s | http_error_rate
metric_sign 表外指标拒绝比较（禁止无符号比较）。改进方向全部以"改善率为正"归一。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p02_common as C  # noqa: E402

import yaml  # noqa: E402


def _ok_reqs(m: dict) -> list[dict]:
    return [r for r in m["per_request"] if r["ok"] and not r["early_stop"]]


def _pct(vals: list[float], q: float) -> float:
    s = sorted(vals)
    if not s:
        raise ValueError("empty")
    k = (len(s) - 1) * q
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def run_metric(run_dir: str, metric: str) -> float:
    m = json.load(open(os.path.join(run_dir, "metrics.json")))
    reqs = _ok_reqs(m)
    if metric == "ttft_p50":
        return _pct([r["ttft_s"] for r in reqs], 0.50)
    if metric == "ttft_p95":
        return _pct([r["ttft_s"] for r in reqs], 0.95)
    if metric == "ttft_p99":
        return _pct([r["ttft_s"] for r in reqs], 0.99)
    if metric == "tpot_p50":
        return statistics.median([r["tpot_s"] for r in reqs if r.get("tpot_s")])
    if metric == "e2e_p50":
        return statistics.median([r["e2e_latency_s"] for r in reqs])
    if metric == "goodput_rps":
        return m["requests_ok"] / m["aggregate"]["batch_wall_s"]
    if metric == "aggregate_tok_s":
        return m["aggregate"]["aggregate_output_tok_s"]
    if metric == "http_error_rate":
        return m["http_errors"] / max(m["requests_total"], 1)
    raise SystemExit(f"unknown metric {metric}")


def layer(runs: list[str], metric: str) -> dict:
    vals = [run_metric(d, metric) for d in runs]
    med = statistics.median(vals)
    return {"values": [round(v, 6) for v in vals], "median": round(med, 6),
            "spread_ratio": round((max(vals) - min(vals)) / med, 4) if med else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", default=os.path.join(os.path.dirname(HERE), "repro", "gates-phase02.yaml"))
    ap.add_argument("--label", required=True)
    ap.add_argument("--scalar", action="store_true")
    ap.add_argument("--policy", action="store_true")
    ap.add_argument("--ref", nargs="+", required=True)
    ap.add_argument("--cand", nargs="+", required=True)
    ap.add_argument("--primary", nargs="+", required=True)
    ap.add_argument("--other", nargs="*", default=[])
    ap.add_argument("--policy-json")
    ap.add_argument("--out")
    args = ap.parse_args()

    gates = yaml.safe_load(open(args.gates))
    sign_table = gates["metric_sign"]
    sg = gates["scalar_optimization_gate"]
    imin = sg["improvement_min"]
    omax = sg["other_axis_regression_max"]

    report: dict = {"label": args.label, "gate_class": "scalar" if args.scalar else "policy",
                    "ref": args.ref, "cand": args.cand,
                    "spread_max_expected": gates["qualify_protocol"]["qualify"]["spread_max"]}

    primary_imp, other_imp = {}, {}
    for met in args.primary + args.other:
        ref_l, cand_l = layer(args.ref, met), layer(args.cand, met)
        sign = C.sign_of(met, sign_table)
        imp = C.improvement(ref_l["median"], cand_l["median"], sign)
        entry = {"ref": ref_l, "cand": cand_l, "sign": sign, "improvement": round(imp, 4)}
        (primary_imp if met in args.primary else other_imp)[met] = entry
    report["metrics"] = {"primary": primary_imp, "other": other_imp}

    if args.scalar:
        verdict = C.screen_decision_scalar(
            {k: v["improvement"] for k, v in primary_imp.items()}, imin, omax,
            {k: v["improvement"] for k, v in other_imp.items()})
    else:
        if not args.policy_json:
            SystemExit("--policy 需要 --policy-json（方向约束机器判定输入）")
        pj = json.loads(args.policy_json)
        bools = {k: v for k, v in pj.items() if isinstance(v, bool)}
        verdict = {"gate": "policy_envelope（约束见 gates-phase02.yaml:directions）",
                   "constraints": pj,
                   "decision": "IN" if all(bools.values()) else "OUT"}
    report["verdict"] = verdict

    txt = json.dumps(report, indent=1, ensure_ascii=False)
    print(txt)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        open(args.out, "w").write(txt + "\n")
    print("SCREEN_" + verdict["decision"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

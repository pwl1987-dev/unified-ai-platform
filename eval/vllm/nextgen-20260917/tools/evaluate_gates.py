#!/usr/bin/env python3
"""Phase 00 Gate 评估器 — 消费 repro/gates-phase00.yaml，输出机器判定结果。

用法: evaluate_gates.py --anchor A1 --runs <dir1> <dir2> <dir3> [--pair-anchor A3 --pair-runs ...]
      evaluate_gates.py --anchor A2 --runs ... [--reference 197.5]
      evaluate_gates.py --repetition-layer --metric client_observed_decode_tok_s --runs ...
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)


def run_metric(run_dir: str, metric: str) -> float | None:
    m = json.load(open(os.path.join(run_dir, "metrics.json")))
    if metric == "aggregate_output_tok_s":
        return m["aggregate"].get("aggregate_output_tok_s")
    if metric == "ttft_s":
        vals = [r["ttft_s"] for r in m["per_request"] if r["ok"] and not r["early_stop"]]
        return statistics.median([v for v in vals if v is not None]) if vals else None
    if metric in ("client_observed_decode_tok_s", "e2e_output_tok_s"):
        vals = [r.get(metric) for r in m["per_request"]
                if r["ok"] and not r["early_stop"]]
        vals = [v for v in vals if v is not None]
        return statistics.median(vals) if vals else None
    raise SystemExit(f"unknown metric {metric}")


def rep_layer(runs: list[str], metric: str) -> dict:
    vals = [run_metric(d, metric) for d in runs]
    if any(v is None for v in vals):
        return {"metric": metric, "values": vals, "error": "missing values"}
    med = statistics.median(vals)
    return {"metric": metric, "values": vals, "median": round(med, 4),
            "min": min(vals), "max": max(vals),
            "spread_ratio": round((max(vals) - min(vals)) / med, 4) if med else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", help="A1|A2|A3|A4")
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--reference", type=float)
    ap.add_argument("--tolerance-pct", type=float, default=5.0)
    ap.add_argument("--stability-max", type=float, default=0.05)
    ap.add_argument("--metric", default="client_observed_decode_tok_s")
    ap.add_argument("--pair-anchor")
    ap.add_argument("--pair-runs", nargs="+")
    ap.add_argument("--c4-validity", action="store_true")
    args = ap.parse_args()

    out: dict = {"anchor": args.anchor, "runs": args.runs}

    # run 级有效性
    run_valid = []
    for d in args.runs:
        m = json.load(open(os.path.join(d, "metrics.json")))
        ok = (m["requests_ok"] == m["requests_total"]
              and m["count_mismatch_samples"] == 0 and m["http_errors"] == 0
              and all(m["sampler_stats"][k]["sampler_exit_code"] == 0
                      for k in ("metrics_endpoint", "nvml")))
        if args.c4_validity:
            mr = m["aggregate"].get("max_running_observed")
            ok = ok and mr == m["concurrency"]
        run_valid.append(ok)
    out["run_validity"] = dict(zip(args.runs, run_valid))

    layer = rep_layer(args.runs, args.metric)
    out["repetition_layer"] = layer

    verdict = {"all_runs_valid": all(run_valid)}
    if "median" in layer:
        verdict["stability_pass"] = (layer["spread_ratio"] is not None
                                     and layer["spread_ratio"] <= args.stability_max)
        if args.reference is not None:
            dev = abs(layer["median"] - args.reference) / args.reference * 100
            verdict["deviation_pct"] = round(dev, 2)
            verdict["reference"] = args.reference
            verdict["consistency"] = ("HIGHLY_CONSISTENT" if dev <= 3.0
                                      else "DRIFT_ALLOWED" if dev <= args.tolerance_pct
                                      else "OVER_DRIFT_BLOCK")
    # fixed-output 完整性
    complete = True
    for d in args.runs:
        m = json.load(open(os.path.join(d, "metrics.json")))
        if m.get("mode") == "fixed-output" and (
                m["early_stop_samples"] > 0
                or any((r.get("output_tokens") or 0) != m["requested_output_tokens"]
                       for r in m["per_request"] if r["ok"])):
            complete = False
    verdict["fixed_output_complete"] = complete

    if args.pair_runs and args.pair_anchor:
        sys.path.insert(0, HERE)
        from pairing_check import load, PAIR_KEYS  # noqa: E402
        a, b = load(args.runs[0]), load(args.pair_runs[0])
        diffs = {k: [a.get(k), b.get(k)] for k in PAIR_KEYS if a.get(k) != b.get(k)}
        verdict["pairing"] = {"with": args.pair_anchor, "paired": not diffs, "diffs": diffs}

    out["verdict"] = verdict
    print(json.dumps(out, indent=1, ensure_ascii=False))
    passed = (verdict.get("all_runs_valid") and verdict.get("stability_pass", False)
              and verdict.get("fixed_output_complete", True)
              and verdict.get("consistency", "HIGHLY_CONSISTENT") != "OVER_DRIFT_BLOCK"
              and verdict.get("pairing", {}).get("paired", True))
    out["PASS"] = passed
    print("ANCHOR_" + ("PASS" if passed else "FAIL"))
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())

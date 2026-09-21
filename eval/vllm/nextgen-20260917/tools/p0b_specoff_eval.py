#!/usr/bin/env python3
"""Phase 03 P0B.1 — spec-off 正式 A/B 判定（gates l2_finalization.spec_off_ab）。

数据源：raw/staging/V29-T2-P0B-{ARM}R{n}-L36K-{sfx}-{MODE}-B01-R*/metrics.json
  per_request.{client_observed_decode_tok_s, ttft_s, tpot_s} + aggregate.aggregate_output_tok_s
判定：spec-off 主轴（P32K decode 或 aggregate）sign-aware ≥3% ∧ 其他轴退步 ≤5%
      ∧ 臂内 spread ≤3% → composite_L2 修订（spec off）；否则维持 spec-on。
"""
from __future__ import annotations

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
STAGING = os.path.join(NEXTGEN, "raw", "staging")
ARMS = ("SPECON", "SPECOFF")


def runs_of(arm: str, sfx: str, mode: str):
    pref = f"V29-T2-P0B-{arm}R"
    for d in sorted(os.listdir(STAGING)):
        if d.startswith(pref) and f"-L36K-{sfx}-{mode}-B01-R" in d:
            p = os.path.join(STAGING, d, "metrics.json")
            try:
                yield json.load(open(p))
            except (OSError, json.JSONDecodeError):
                continue


def per_req(arm, sfx, mode, field) -> list[float]:
    out = []
    for m in runs_of(arm, sfx, mode):
        for rq in m.get("per_request", []):
            v = rq.get(field)
            if rq.get("ok") and isinstance(v, (int, float)):
                out.append(float(v))
    return out


def agg_tok(arm, sfx, mode) -> list[float]:
    return [float(m["aggregate"]["aggregate_output_tok_s"]) for m in runs_of(arm, sfx, mode)
            if m.get("aggregate", {}).get("aggregate_output_tok_s") is not None]


def main() -> int:
    rep = json.load(open(os.path.join(STAGING, "PH3-P0B", "specoff-certify-report.json")))
    rounds = rep.get("rounds", [])
    done = {(r["arm"], r["round"]): (r["entry"] or {}).get("done") for r in rounds}
    if not all(done.get((a, i)) for a in ARMS for i in (1, 2, 3)):
        print(json.dumps({"verdict": "INCOMPLETE", "done": {str(k): v for k, v in done.items()}}))
        return 1

    def med(v): return statistics.median(v) if v else None
    def spread(v): return (max(v) - min(v)) / med(v) if len(v) > 1 and med(v) else None

    ax = {}
    for arm in ARMS:
        dec = per_req(arm, "C1-L032K", "NS", "client_observed_decode_tok_s")
        cttft = per_req(arm, "C1-L032K", "NS", "ttft_s")
        wttft = per_req(arm, "WARM", "NS", "ttft_s")
        tpot = per_req(arm, "C1-L032K", "NS", "tpot_s")
        agg = agg_tok(arm, "C1-L032K", "NS")
        d565 = per_req(arm, "C1-L0565", "F512", "client_observed_decode_tok_s")
        ax[arm] = {
            "p32k_cold_decode": {"n": len(dec), "vals": [round(x, 2) for x in dec], "median": med(dec), "spread": spread(dec)},
            "p32k_cold_agg": {"n": len(agg), "vals": [round(x, 2) for x in agg], "median": med(agg)},
            "p32k_cold_ttft": {"n": len(cttft), "vals": [round(x, 3) for x in cttft], "median": med(cttft)},
            "p32k_warm_ttft": {"n": len(wttft), "vals": [round(x, 3) for x in wttft], "median": med(wttft)},
            "p32k_tpot": {"n": len(tpot), "vals": [round(x, 4) for x in tpot], "median": med(tpot)},
            "d565_decode": {"n": len(d565), "vals": [round(x, 2) for x in d565], "median": med(d565)},
        }

    def imp(ref, cand, sign):
        if ref in (None, 0) or cand is None:
            return None
        return (ref - cand) / ref if sign == "lower" else (cand - ref) / ref

    on, off = ax["SPECON"], ax["SPECOFF"]
    improvements = {
        "p32k_cold_decode": imp(on["p32k_cold_decode"]["median"], off["p32k_cold_decode"]["median"], "higher"),
        "p32k_cold_agg": imp(on["p32k_cold_agg"]["median"], off["p32k_cold_agg"]["median"], "higher"),
        "p32k_cold_ttft": imp(on["p32k_cold_ttft"]["median"], off["p32k_cold_ttft"]["median"], "lower"),
        "p32k_warm_ttft": imp(on["p32k_warm_ttft"]["median"], off["p32k_warm_ttft"]["median"], "lower"),
        "p32k_tpot": imp(on["p32k_tpot"]["median"], off["p32k_tpot"]["median"], "lower"),
        "d565_decode": imp(on["d565_decode"]["median"], off["d565_decode"]["median"], "higher"),
    }
    spreads_ok = all((ax[a]["p32k_cold_decode"]["spread"] or 0) <= 0.03 for a in ARMS) \
        and all(ax[a]["p32k_cold_decode"]["n"] >= 9 for a in ARMS)
    primary_pass = any(v is not None and v >= 0.03
                       for k, v in improvements.items()
                       if k in ("p32k_cold_decode", "p32k_cold_agg"))
    regression_ok = all(v is None or v >= -0.05
                        for k, v in improvements.items()
                        if k in ("d565_decode", "p32k_cold_ttft", "p32k_warm_ttft"))
    verdict = "COMPOSITE_L2_REVISED_TO_SPEC_OFF" \
        if (primary_pass and regression_ok and spreads_ok) else "MAINTAIN_SPEC_ON"
    out = {"axes": ax, "improvements_specoff_vs_specon": improvements,
           "spread_ok": spreads_ok, "primary_pass": primary_pass,
           "other_axis_regression_ok": regression_ok, "verdict": verdict,
           "rule": "主轴 ≥3% ∧ 其他轴退步 ≤5% ∧ 臂内 spread ≤3%（gates l2_finalization）"}
    json.dump(out, open(os.path.join(STAGING, "PH3-P0B", "specoff-decision.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v)
                      for k, v in improvements.items()} | {"verdict": verdict,
                      "spreads_ok": spreads_ok}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""ph5_matrix_eval.py — Phase 05 cell 证据 → ph5-matrix.json（ph5_gate_e 输入）。

聚合源（staging 目录实名约定）：
  direct 轨    raw/staging/V29-PH5-<TOPO>-<CELL>-<MODE>-B<r>-R<i>/metrics.json
  router 轨    raw/staging/V29-PH5R-<TOPO>-...
  多会话/混合  raw/staging/PH5-P1/<scenario>-<TOPO>*/cell-summary.json
规则：median over (reps × boots)；CAPACITY_LIMIT/UNSUPPORTED 直通；缺失=不出键（judge 判 NOT_AVAILABLE）。
输出：raw/staging/PH5-P3/ph5-matrix.json {topologies:[...], cells:{axis:{topo:val}}, provenance:{...}}
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics

ST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw", "staging")

# cell 目录名 → (matrix 轴名, 提取器后缀)
DIRECT_MAP = {
    r"C1-L0565": ("d565_c1_decode", "F512"),
    r"C1-L032K": ("p32k_c1_decode", "NS"),
    r"C1-L128K[TT]?": ("p128k_c1_decode", "NS"),
    r"C4-L004K": ("p4k_c4_agg", "NS"),
    r"C8-L0565": ("d565_c8_goodput", "F512"),
    r"C16-L0565": ("d565_c16_goodput", "F512"),
    r"C8-L004K": ("p4k_c8_goodput", "NS"),
    r"C16-L004K": ("p4k_c16_goodput", "NS"),
}


def med_from_metrics(dirs: list[str]) -> dict:
    vals = {"decode": [], "agg": [], "ttft": [], "goodput": [], "http_err": 0, "n_ok": 0, "n": 0}
    for d in dirs:
        mp = os.path.join(d, "metrics.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        vals["n"] += 1
        vals["n_ok"] += m.get("requests_ok") or 0
        vals["http_err"] += m.get("http_errors") or 0
        pr = [r for r in (m.get("per_request") or []) if r.get("ok")]
        dec = [r.get("client_observed_decode_tok_s") for r in pr
               if r.get("client_observed_decode_tok_s")]
        if dec:
            vals["decode"].append(statistics.median(dec))
        agg = (m.get("aggregate") or {}).get("aggregate_output_tok_s")
        if agg:
            vals["agg"].append(agg)
        tt = [r.get("ttft_s") for r in pr if r.get("ttft_s") is not None]
        if tt:
            vals["ttft"].append(statistics.median(tt))
        wall = (m.get("aggregate") or {}).get("batch_wall_s")
        if wall and (m.get("requests_ok") or 0):
            vals["goodput"].append((m.get("requests_ok")) / wall)
    out = {}
    if vals["decode"]:
        out["decode"] = round(statistics.median(vals["decode"]), 3)
    if vals["agg"]:
        out["agg"] = round(statistics.median(vals["agg"]), 3)
    if vals["ttft"]:
        out["ttft"] = round(statistics.median(vals["ttft"]), 4)
    if vals["goodput"]:
        out["goodput_rps"] = round(statistics.median(vals["goodput"]), 4)
    out["n_dirs"] = vals["n"]
    out["http_err"] = vals["http_err"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topologies", default="T1F,T2F,T1,T2,T3,T4")
    ap.add_argument("--out", default=os.path.join(ST, "PH5-P3", "ph5-matrix.json"))
    args = ap.parse_args()
    topos = args.topologies.split(",")
    cells: dict[str, dict[str, object]] = {}
    prov: dict[str, list[str]] = {}
    for topo in topos:
        for pat, (axis, modesuffix) in DIRECT_MAP.items():
            for track, tdir in (("direct", "V29-PH5-"), ("router", "V29-PH5R-")):
                dirs = sorted(glob.glob(os.path.join(
                    ST, f"{tdir}{topo}-*{pat}*{modesuffix}*-B*-R*")))
                if not dirs:
                    continue
                r = med_from_metrics(dirs)
                if r.get("n_dirs"):
                    key = axis if track == "direct" else axis + "_router"
                    # 轴语义：*_decode 轴=per-request client decode 中位；goodput 轴=ok/s；
                    # 其余聚合轴=aggregate_output_tok_s 中位
                    if axis.endswith("_decode"):
                        val = r.get("decode")
                    elif axis.endswith("_goodput"):
                        val = r.get("goodput_rps")
                    else:
                        val = r.get("agg")
                    if val is not None:
                        cells.setdefault(key, {})[topo] = val
                    if track == "direct" and "ttft" in r and axis.endswith("_decode"):
                        cells.setdefault(axis[:-len("_decode")] + "_ttft", {})[topo] = r["ttft"]
                    prov[f"{topo}:{axis}:{track}"] = [os.path.relpath(d, ST) for d in dirs][:12]
    # 场景类 cell-summary（multi/sticky/failover/mixed）
    for f in glob.glob(os.path.join(ST, "PH5-P1", "*", "cell-summary.json")) + \
             glob.glob(os.path.join(ST, "PH5-P3", "*", "cell-summary.json")):
        cs = json.load(open(f))
        name = os.path.basename(os.path.dirname(f))
        m = re.match(r"(dual|dual128|four|mixed|sticky|failover)-?(T\d\w*)?$", name)
        if not m:
            continue
        scen, topo = m.group(1), m.group(2) or "T?"
        d = cs.get("sessions") or {}
        toks = [v.get("sum_output_tokens") or 0 for v in d.values()]
        walls = [v.get("batch_wall_s") or 1 for v in d.values()]
        if scen == "dual" or scen == "dual128":
            pre = "dual_p32k" if scen == "dual" else "dual_p128k"
            if toks:
                cells.setdefault(pre + "_sess_decode", {})[topo] = round(
                    statistics.median([t / w for t, w in zip(toks, walls)]), 3)
                cells.setdefault(pre + "_aggregate", {})[topo] = round(sum(toks) / max(walls), 3)
                cells.setdefault(pre + "_fairness", {})[topo] = cs.get("fairness_jain_goodput")
        elif scen == "four":
            if toks:
                cells.setdefault("four_p32k_aggregate", {})[topo] = round(sum(toks) / max(walls), 3)
                cells.setdefault("four_p32k_fairness", {})[topo] = cs.get("fairness_jain_goodput")
        elif scen == "mixed":
            long_ok = any(k == "long" and (v.get("requests_ok") or 0) >= 1 for k, v in d.items())
            short_p95 = max((v.get("ttft_max") or 0) for k, v in d.items() if k.startswith("s"))
            base = (cells.get("d565_c1_ttft", {}).get(topo))
            guard = bool(base and short_p95 and short_p95 <= base * 1.05 + 0.05)
            cells.setdefault("mixed_short_p95_ttft_guard", {})[topo] = guard
            cells.setdefault("mixed_long_completion_rate", {})[topo] = 1.0 if long_ok else 0.0
            cells.setdefault("mixed_aggregate", {})[topo] = cs.get("aggregate_tok_s")
            cells.setdefault("mixed_short_p95_ttft_s", {})[topo] = round(short_p95, 4)
    out = {"topologies": topos, "cells": cells, "provenance": prov,
           "note": "CAPACITY_LIMIT/UNSUPPORTED 由 boot/容量快照侧另行并入（gate_e 支配判定）"}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"cells": {k: v for k, v in list(cells.items())[:8]},
                      "n_axes": len(cells)}, ensure_ascii=False)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

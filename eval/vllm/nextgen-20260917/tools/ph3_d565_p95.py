#!/usr/bin/env python3
"""Phase 03 P3 — D565 open p95 认证级重跑（Phase 02 遗留：Screen 级小样本非单调）。

2 evidence boots × 认证参数（measurement 600s=2×、min_completed 200=3.3×，其余同
gates-phase03 slo_curve_params.D565）；每 boot：closed C1/C2/C4/C8 快测 → sat_est →
open 0.25/0.5/0.75/0.9/1.1× 五点。判读：p95 随 arrival 单调（Spearman）或如实确认为
真实非单调特性（跨 boot 一致即非噪声）。断点续跑 stages=boot1/boot2。
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import p1_batch2_openloop as ol  # noqa: E402
import p4_slo_chain as p4  # noqa: E402
from gen_fixtures import make_prompt  # noqa: E402
from p02_screen import stop  # noqa: E402

STAGING = os.path.join(NG, "raw", "staging")
REPORT = os.path.join(STAGING, "PH3-GATEC", "d565-p95-rerun.json")
RATIOS = (0.25, 0.50, 0.75, 0.90, 1.10)
PRM = {"prompt_tokens": 512, "max_tokens": 256, "warmup_s": 120, "measure_s": 600,
       "min_completed": 200, "max_test_s": 1500}   # 认证参数：2× 窗 / 3.3× 样本


def curve_once(key: str) -> dict:
    info, pid, pgid = p4.run_boot(f"D565P95-{key}", p4.L36, "B01")
    if not info:
        return {"error": "BOOT_FAIL"}
    api = "http://127.0.0.1:19702/v1"
    base = api.rsplit("/v1", 1)[0]
    ptext = make_prompt(PRM["prompt_tokens"])
    poller = ol.MetricsPoller(base)
    poller.start()
    cl = {}
    for conc in (1, 2, 4, 8):
        cl[str(conc)] = ol.closed_loop(api, ptext, PRM["max_tokens"], conc, 2,
                                       f"d565p95-{key}", 300)
    sat = ol.saturation_est(cl, PRM["max_tokens"])
    if sat <= 0.01:   # 防 0 速率：expovariate(0) 族线程静默死
        sat = 0.05
    print(f"[{key}] closed done, sat_est={sat:.4f}", flush=True)
    points = []
    for ratio in RATIOS:
        pt = ol.open_point(api, ptext, PRM["max_tokens"], sat * ratio, PRM,
                           f"{key}-r{ratio}", poller)
        points.append(pt)
        print(json.dumps({k: pt.get(k) for k in ("arrival_rate", "served_ok", "ttft_p95")}),
              flush=True)
    poller.stop_flag = True
    stop(pgid)
    time.sleep(5)
    return {"info": info, "closed": cl, "sat_est": round(sat, 4), "open": points}


def spearman_monotone(points: list[dict]) -> dict:
    xs = [p.get("arrival_rate") for p in points]
    ys = [p.get("ttft_p95") for p in points if isinstance(p.get("ttft_p95"), (int, float))]
    pts = [(p["arrival_rate"], p["ttft_p95"]) for p in points
           if isinstance(p.get("arrival_rate"), (int, float))
           and isinstance(p.get("ttft_p95"), (int, float))]
    if len(pts) < 3:
        return {"monotone": None, "note": "样本不足"}
    pts.sort()
    ranks_y = [sorted(y for _, y in pts).index(y) + 1 for _, y in pts]
    ranks_x = list(range(1, len(pts) + 1))
    n = len(pts)
    d2 = sum((a - b) ** 2 for a, b in zip(ranks_x, ranks_y))
    rho = 1 - 6 * d2 / (n * (n * n - 1))
    return {"spearman_rho": round(rho, 3), "monotone": rho > 0.8,
            "points": [(round(a, 3), round(b, 3)) for a, b in pts]}


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"boots": {}}
    for k in ("boot1", "boot2"):
        if k not in doc["boots"] or doc["boots"][k].get("error") == "BOOT_FAIL":
            doc["boots"][k] = curve_once(k.upper())
            json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    verdicts = {k: spearman_monotone(v.get("open", [])) for k, v in doc["boots"].items()}
    both = [v.get("monotone") for v in verdicts.values()]
    doc["p95_monotonicity"] = {
        "per_boot": verdicts,
        "conclusion": ("NON_MONOTONIC_CONFIRMED（跨 boot 一致——真实特性，非样本噪声）"
                       if all(m is False for m in both)
                       else "MONOTONE_OR_MIXED（详见 per_boot）"),
        "params": PRM,
    }
    json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(doc["p95_monotonicity"], ensure_ascii=False)[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

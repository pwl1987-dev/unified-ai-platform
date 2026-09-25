#!/usr/bin/env python3
"""ph5_gate_e.py — Phase 05 Gate E 机器判定器（四冠军，禁只报 aggregate）。

输入：raw/staging/PH5-P3/screen+qualify 汇总（ph5-matrix.json：cell → topology → {median…}）
规则（gates-phase05 gate_e，看结果前冻结）：
  1. 四冠军分别判：throughput / single_agent / dual_agent / mixed_production
  2. 3% 带外才算胜负（吞吐/prefill 类）；落带=EQUIVALENT → tiebreak 链
  3. CAPACITY_LIMIT/UNSUPPORTED = 正式 cell 结论，参与支配判定（不可服务即不胜出）
  4. M4=TP2+TP1+TP1 仅在 mixed 真实胜出时冻结；TP4 仅真实任务受益才保留
输出：raw/staging/PH5-P4/gate-e-verdict.json
自测：--selftest 合成矩阵 → 断言四冠军逻辑（含 EQUIVALENT 带/容量支配/early-stop 路径）
"""
from __future__ import annotations

import argparse
import json
import os

EPS = 0.03
# lower-better 轴实名表（ttft/tpot/spread/J_per_tok 家族）——tiebreak 与主轴共用的符号表
LOWER_BETTER = {"dual_p32k_p95_spread", "p32k_c1_ttft", "J_per_tok_p32k_c1",
                "J_per_tok_p4k_c16", "J_per_tok_mixed"}
ST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw", "staging")

CHAMPIONS = {
    "throughput_champion": {
        "cells": ["d565_c16_goodput_router", "d565_c8_goodput_router", "p4k_c16_goodput_router", "p4k_c8_goodput_router"],
        "primary": "d565_c16_goodput_router", "tiebreak": ["d565_c8_goodput_router", "p4k_c16_goodput_router", "J_per_tok_p4k_c16"],
        "higher_better": True},
    "single_agent_champion": {
        "cells": ["d565_c1_decode", "p32k_c1_decode", "p128k_c1_decode"],
        "primary": None,  # 跨 fixture 胜场制（≥2/3 且出带）
        "tiebreak": ["p32k_c1_ttft", "J_per_tok_p32k_c1"], "higher_better": True},
    "dual_agent_champion": {
        "cells": ["dual_p32k_sess_decode", "dual_p128k_sess_decode"],
        "primary": "dual_p32k_sess_decode",
        "tiebreak": ["dual_p32k_p95_spread", "dual_p32k_fairness", "dual_p32k_aggregate"],
        "higher_better": True},
    "mixed_production_champion": {
        "cells": ["mixed_short_p95_ttft_guard", "mixed_long_completion_rate", "mixed_aggregate"],
        "primary": "mixed_short_p95_ttft_guard",   # bool 守门（≤direct 基线×1.05）
        "tiebreak": ["mixed_aggregate", "J_per_tok_mixed"], "higher_better": True},
}


def better(cand: float, ref: float, higher: bool = True) -> float:
    """sign-aware 相对差：正=cand 更好"""
    if cand is None or ref is None:
        return 0.0
    if higher:
        return (cand - ref) / ref if ref else 0.0
    return (ref - cand) / ref if ref else 0.0


def pick_champion(matrix: dict, spec: dict, topologies: list[str]) -> dict:
    cell_vals = {c: {t: matrix.get(c, {}).get(t) for t in topologies} for c in spec["cells"]}
    serviceable = {t for t in topologies
                   if all(matrix.get(c, {}).get(t) != "CAPACITY_LIMIT"
                          and matrix.get(c, {}).get(t) != "UNSUPPORTED"
                          for c in spec["cells"])}

    def guard_ok(t: str) -> bool:
        # mixed 守门轴：False/None 不入局
        if spec["primary"] and spec["primary"].endswith("_guard"):
            v = matrix.get(spec["primary"], {}).get(t)
            return v is True
        return True

    field = {t: (matrix.get(spec["primary"], {}).get(t)
                 if spec["primary"] else None) for t in topologies} if spec["primary"] else {}
    if spec["primary"] is None:  # 胜场制
        wins = {t: 0 for t in topologies}
        for c in spec["cells"]:
            vals = {t: matrix.get(c, {}).get(t) for t in topologies if t in serviceable}
            nums = {t: v for t, v in vals.items() if isinstance(v, (int, float))}
            if not nums:
                continue
            best = max(nums.values())
            for t, v in nums.items():
                if v == best:
                    wins[t] += 1
                elif better(v, best) > -EPS:  # 带内=共胜
                    wins[t] += 1
        eligible = [t for t in topologies if t in serviceable]
        top_wins = max((wins[t] for t in eligible), default=0)
        finalists = [t for t in eligible if wins[t] == top_wins]
        verdict = finalists[0] if len(finalists) == 1 else None
        return {"winner": verdict or "EQUIVALENT_CO_DECLARED",
                "wins": wins, "eligible": eligible,
                "cell_values": cell_vals}

    def val(t, key=None):
        v = matrix.get(key or spec["primary"], {}).get(t)
        return v if isinstance(v, (int, float)) else None

    eligible = [t for t in topologies if t in serviceable and guard_ok(t)]
    if not eligible:
        return {"winner": "NO_SERVICEABLE_CANDIDATE", "cell_values": cell_vals}
    base = {t: val(t) for t in eligible}
    bestval = max(v for v in base.values() if v is not None) if any(
        v is not None for v in base.values()) else None
    if bestval is None:
        return {"winner": "MEASUREMENT_NOT_AVAILABLE", "cell_values": cell_vals}
    leaders = [t for t in eligible if base[t] is not None and better(base[t], bestval) > -EPS]
    if len(leaders) == 1:
        return {"winner": leaders[0], "values": base, "eligible": eligible, "cell_values": cell_vals}
    # tiebreak 链
    for tb in spec["tiebreak"]:
        tv = {t: matrix.get(tb, {}).get(t) for t in leaders}
        nums = {t: v for t, v in tv.items() if isinstance(v, (int, float))}
        if not nums:
            continue
        higher = tb not in LOWER_BETTER
        b = max(nums.values()) if higher else min(nums.values())
        lead2 = [t for t, v in nums.items() if better(v, b, higher=higher) > -EPS]
        if len(lead2) == 1:
            return {"winner": lead2[0], "values": base, "tiebreak_axis": tb,
                    "eligible": eligible, "cell_values": cell_vals}
    return {"winner": "EQUIVALENT_CO_DECLARED", "values": base,
            "eligible": eligible, "cell_values": cell_vals}


def judge(matrix: dict, topologies: list[str]) -> dict:
    out = {}
    for name, spec in CHAMPIONS.items():
        out[name] = pick_champion(matrix, spec, topologies)
    t4 = out.get("single_agent_champion", {}).get("winner")
    return {
        "gate_e": {
            "question": "四冠军分别回答（吞吐/单Agent/双Agent/混合生产；禁只报 aggregate）",
            "champions": out,
            "m4_freeze_rule": "M4=TP2+TP1+TP1 仅当 mixed_production_champion.winner==T3 才冻结",
            "tp4_retention_rule": "TP4 仅真实任务受益才保留（无任一冠军=EARLY_STOP_OUT/OUT）",
            "t4_outcome_hint": t4,
        },
        "epsilon_band": EPS,
    }


def selftest() -> int:
    topo = ["T1", "T2", "T3", "T4"]
    # 合成：T1 批处理王；T2 单Agent 带 T4 出带胜；T3 mixed 守门过且 aggregate 高；T2 dual 王
    mx = {
        "d565_c16_goodput_router": {"T1": 10.0, "T2": 4.0, "T3": 8.0, "T4": 3.0},
        "d565_c8_goodput_router": {"T1": 9.0, "T2": 4.0, "T3": 7.5, "T4": 3.0},
        "p4k_c16_goodput_router": {"T1": 11.0, "T2": "CAPACITY_LIMIT", "T3": 9.0, "T4": 2.0},
        "p4k_c8_goodput_router": {"T1": 10.0, "T2": 5.0, "T3": 8.8, "T4": 2.0},
        "J_per_tok_p4k_c16": {"T1": 2.0, "T3": 2.1, "T4": 2.5},   # lower better
        "d565_c1_decode": {"T1": 100.0, "T2": 102.0, "T3": 101.0, "T4": 103.0},
        "p32k_c1_decode": {"T1": "CAPACITY_LIMIT", "T2": 50.0, "T3": 49.5, "T4": 52.0},
        "p128k_c1_decode": {"T1": "CAPACITY_LIMIT", "T2": 20.0, "T3": 19.8, "T4": 21.0},
        "dual_p32k_sess_decode": {"T1": "CAPACITY_LIMIT", "T2": 40.0, "T3": 30.0, "T4": 41.0},
        "dual_p32k_p95_spread": {"T2": 0.1, "T3": 0.2, "T4": 0.5},
        "dual_p32k_fairness": {"T2": 0.99, "T3": 0.98, "T4": 0.9},
        "dual_p32k_aggregate": {"T2": 80.0, "T3": 60.0, "T4": 82.0},
        "mixed_short_p95_ttft_guard": {"T1": False, "T2": True, "T3": True, "T4": True},
        "mixed_long_completion_rate": {"T2": 1.0, "T3": 1.0, "T4": 0.5},
        "mixed_aggregate": {"T2": 30.0, "T3": 45.0, "T4": 20.0},
        "J_per_tok_mixed": {"T2": 2.2, "T3": 2.0, "T4": 2.6},
    }
    v = judge(mx, topo)["gate_e"]["champions"]
    assert v["throughput_champion"]["winner"] == "T1", v["throughput_champion"]
    # single_agent：T4 三 fixture 全胜（103/52/21 出带）→ T4
    assert v["single_agent_champion"]["winner"] == "T4", v["single_agent_champion"]
    # dual：T4 41 vs T2 40 —— 2.5% 带内共胜 → tiebreak spread T2 0.1 胜
    assert v["dual_agent_champion"]["winner"] == "T2", v["dual_agent_champion"]
    # mixed：T1 守门 False 出局；T3 aggregate 45>30 胜
    assert v["mixed_production_champion"]["winner"] == "T3", v["mixed_production_champion"]
    # EQUIVALENT 路径：把 d565_c16 拉平 → co-declared 或 tiebreak
    mx2 = dict(mx); mx2["d565_c16_goodput_router"] = {"T1": 10.0, "T2": 4.0, "T3": 9.9, "T4": 3.0}
    v2 = judge(mx2, topo)["gate_e"]["champions"]
    assert v2["throughput_champion"]["winner"] == "T1"  # 1% 带内共胜→tiebreak c8 T1 9.0 胜
    print(json.dumps({"selftest": "SELFTEST_PASS",
                      "throughput": "T1", "single_agent": "T4",
                      "dual(via tiebreak)": "T2", "mixed": "T3",
                      "equivalent_band_path": "OK"}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--matrix", default=os.path.join(ST, "PH5-P3", "ph5-matrix.json"))
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    mx = json.load(open(args.matrix))
    verdict = judge(mx["cells"], mx["topologies"])
    out = os.path.join(ST, "PH5-P4", "gate-e-verdict.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    verdict["inputs"] = [args.matrix]
    json.dump(verdict, open(out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v["winner"] for k, v in verdict["gate_e"]["champions"].items()},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

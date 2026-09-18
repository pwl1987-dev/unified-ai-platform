#!/usr/bin/env python3
"""p02_common — Phase 02 共享模块：Prometheus 解析（_total 纪律）+ sign-aware 改善率。

自测（P0A.5 义务，Phase 01 §8.9 教训固化）：
  python3 p02_common.py --selftest
合成一段含 `_total` 计数器与 `_created` gauge（值=epoch 秒）的 /metrics body，
断言 counter_total() 只合计 _total 行——把时间戳当计数器的 bug 永不再犯。
"""
from __future__ import annotations

import argparse
import json
import sys


def parse_prometheus(body: str) -> dict[str, float]:
    """精确名解析：'name{labels} value' -> {name: value}（重复名覆盖，TYPE/HELP 行跳过）。"""
    out: dict[str, float] = {}
    for ln in body.splitlines():
        if not ln.startswith("vllm:") and not ln.startswith("#"):
            if not ln.startswith("vllm:"):
                continue
        if ln.startswith("#"):
            continue
        parts = ln.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        try:
            out[parts[0].split("{")[0]] = float(parts[1])
        except ValueError:
            continue
    return out


def counter_total(metrics: dict[str, float], family: str) -> float | None:
    """计数器取值：只认精确名 `<family>_total`（族名自身带 _total 则原样）。

    两条防线（Phase 01 §8.9 教训固化）：
    1. 绝不加 `<family>_created`（Prometheus _created gauge，值=进程启动 epoch 秒）；
    2. 不做前缀族匹配——`vllm:preemption_mode_*_total` 是另一个族，
       前缀求和会把异族计数加进来。
    """
    total_name = family if family.endswith("_total") else family + "_total"
    vals = [v for k, v in metrics.items() if k == total_name]
    return vals[0] if vals else None


def gauge(metrics: dict[str, float], name: str) -> float | None:
    return metrics.get(name)


def improvement(ref: float, cand: float, sign: str) -> float:
    """sign-aware 改善率：lower=(ref−cand)/ref；higher=(cand−ref)/ref。正值=变好。"""
    if sign == "lower":
        return (ref - cand) / ref
    if sign == "higher":
        return (cand - ref) / ref
    raise ValueError(f"unknown sign {sign!r}（metric_sign 表外指标）")


def sign_of(metric: str, metric_sign: dict[str, str]) -> str:
    s = metric_sign.get(metric)
    if s is None:
        raise ValueError(f"metric {metric!r} 不在 metric_sign 表——禁止无符号比较")
    return s


def screen_decision_scalar(primary: dict[str, float], improvement_min: float,
                            other_axis_regression_max: float,
                            other_axes: dict[str, float]) -> dict:
    """scalar_optimization_gate 机器判定。

    primary: {metric: improvement}（sign-aware，已算好）
    other_axes: {metric: improvement}（正=变好；退步=负）
    """
    best = max(primary.values())
    best_axis = max(primary, key=primary.get)
    regress = {a: v for a, v in other_axes.items() if v < -other_axis_regression_max}
    dec = "IN" if (best >= improvement_min and not regress) else "OUT"
    return {"decision": dec, "best_axis": best_axis, "best_improvement": round(best, 4),
            "primary": {k: round(v, 4) for k, v in primary.items()},
            "other_axes": {k: round(v, 4) for k, v in other_axes.items()},
            "regression_violations": regress,
            "gate": {"improvement_min": improvement_min,
                     "other_axis_regression_max": other_axis_regression_max}}


def _selftest() -> int:
    created_epoch = 1_789_706_531.8011827   # Phase 01 事故原值
    body = (
        "# HELP vllm:num_preemptions_total Preemptions\n"
        "# TYPE vllm:num_preemptions_total counter\n"
        "vllm:num_preemptions_total 0.0\n"
        f"vllm:num_preemptions_created {created_epoch}\n"
        "# 异族诱饵：不得被前缀求和进 vllm:preemption 族\n"
        "vllm:preemption_mode_recompute_reemptions_total 2.0\n"
        "vllm:preemption_total 3.0\n"
        "vllm:num_requests_running{model=\"x\"} 4\n"
        "vllm:gpu_cache_usage_perc 0.5\n"
    )
    m = parse_prometheus(body)
    assert m["vllm:num_preemptions_total"] == 0.0
    assert m.get("vllm:num_preemptions_created") == created_epoch
    pt = counter_total(m, "vllm:num_preemptions")
    assert pt == 0.0, f"preempt counter 必须为 0.0，得到 {pt}（_created 泄漏！）"
    assert counter_total(m, "vllm:preemption") == 3.0, "异族前缀泄漏进族合计"
    assert gauge(m, "vllm:num_requests_running") == 4.0
    # sign-aware
    assert improvement(100.0, 97.0, "lower") == 0.03
    assert improvement(100.0, 103.0, "higher") == 0.03
    assert improvement(100.0, 106.0, "lower") == -0.06
    d = screen_decision_scalar({"tpot": 0.04}, 0.03, 0.05, {"ttft_p95": -0.01})
    assert d["decision"] == "IN"
    d2 = screen_decision_scalar({"tpot": 0.04}, 0.03, 0.05, {"ttft_p95": -0.06})
    assert d2["decision"] == "OUT" and d2["regression_violations"] == {"ttft_p95": -0.06}
    print(json.dumps({"selftest": "PASS",
                      "checks": ["parse exact-name", "counter _total-only (created excluded)",
                                 "gauge", "sign-aware improvement", "scalar screen decision"]},
                     ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    ap.error("仅支持 --selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main())

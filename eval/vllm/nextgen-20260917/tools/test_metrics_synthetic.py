#!/usr/bin/env python3
"""合成时间戳单元测试 — 验证 METRICS-SCHEMA 冻结公式（Harness Gate §6.0.2）。

纯手算对照，不依赖网络/GPU。全过输出 SYNTHTEST_PASS。
"""
from __future__ import annotations

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from bench_nextgen import (compute_request_metrics, compute_percentiles_if_enough,
                           compute_percentiles_if_enough as _p)  # noqa: E402

FAILS = []


def check(name, got, want, tol=None):
    ok = (abs(got - want) <= tol) if (tol is not None and got is not None) else (got == want)
    if not ok:
        FAILS.append(f"{name}: got={got} want={want}")
    return ok


# 用例 1：512 token、TTFT 2.0s、总 10.0s
#   e2e = 512/10 = 51.2 ; decode = (512-1)/(10-2) = 63.875 ; tpot = 8/511
ev = {"request_index": 0, "ok": True, "request_start": 100.0,
      "first_header": 100.5, "first_token": 102.0, "last_token": 110.0,
      "output_tokens": 512, "early_stop": False, "stop_reason": "length"}
r = compute_request_metrics(ev)
check("1 ttfb", r["ttfb_s"], 0.5, 1e-6)
check("1 ttft", r["ttft_s"], 2.0, 1e-6)
check("1 e2e_latency", r["e2e_latency_s"], 10.0, 1e-6)
check("1 e2e_tok_s", r["e2e_output_tok_s"], 51.2, 1e-3)
check("1 decode_tok_s", r["client_observed_decode_tok_s"], 511 / 8, 1e-3)
check("1 tpot", r["tpot_s"], 8 / 511, 1e-6)
check("1 null_reason", r["null_reason"], None)

# 用例 2：单 token => decode/tpot null + INSUFFICIENT_TOKENS（禁 0/NaN）
ev2 = {"request_index": 1, "ok": True, "request_start": 0.0,
       "first_header": 0.1, "first_token": 1.0, "last_token": 1.0,
       "output_tokens": 1, "early_stop": False, "stop_reason": "stop"}
r2 = compute_request_metrics(ev2)
check("2 decode null", r2["client_observed_decode_tok_s"], None)
check("2 tpot null", r2["tpot_s"], None)
check("2 reason", r2["null_reason"], "INSUFFICIENT_TOKENS")
check("2 e2e present", r2["e2e_output_tok_s"], 1.0, 1e-6)

# 用例 3：失败请求 => 全 null
r3 = compute_request_metrics({"request_index": 2, "ok": False})
check("3 failed all null", (r3["ttft_s"], r3["e2e_output_tok_s"]), (None, None))

# 用例 4：193 token 自然停止（D565 TP1 历史形态：~133.5 tok/s e2e 口径）
#   wall=193/133.46=1.4462s；用整数时刻近似：first=0.9, last=1.4462
ev4 = {"request_index": 3, "ok": True, "request_start": 0.0,
       "first_header": 0.2, "first_token": 0.9, "last_token": 1.4462,
       "output_tokens": 193, "early_stop": False, "stop_reason": "stop"}
r4 = compute_request_metrics(ev4)
check("4 e2e ~133.46", r4["e2e_output_tok_s"], 133.46, 0.02)
check("4 decode", r4["client_observed_decode_tok_s"], 192 / (1.4462 - 0.9), 1e-2)

# 用例 5：分位数两层口径 —— 3 个请求不得产出 P95
three = [compute_request_metrics({**ev, "request_index": i}) for i in range(3)]
check("5 <20 samples no pct", compute_percentiles_if_enough(three), {})
# 20+ 请求产出分位数且单调
many = []
for i in range(21):
    e = {**ev, "request_index": i, "first_token": 1.0 + i * 0.1, "last_token": 10.0}
    many.append(compute_request_metrics(e))
pct = compute_percentiles_if_enough(many)
check("5 p50<=p95<=p99", pct["ttft_p50_s"] <= pct["ttft_p95_s"] <= pct["ttft_p99_s"], True)

print("\n".join(FAILS) if FAILS else "all synthetic cases passed")
print("SYNTHTEST_" + ("FAIL" if FAILS else "PASS"))
sys.exit(1 if FAILS else 0)

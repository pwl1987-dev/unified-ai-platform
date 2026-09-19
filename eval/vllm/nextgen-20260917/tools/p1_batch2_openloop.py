#!/usr/bin/env python3
"""P1-SCR-BATCH2 单元工具 B：admission 开环（policy_envelope_gate 约束取证）。

协议（Screen 级；全量冻结参数留给 P4 SLO 曲线）：
  closed 阶段 C∈{1,2,4,8}×2 reps → 饱和速率估计（复用 p5_openloop 思路）
  open 阶段 ratios=[0.9, 1.1]（gates 冻结过载点），Poisson 到达、逐请求唯一 salt（纯冷形态）
取证面（对应 gates.admission_control.judgement）：
  served ttft p50/p95（仅 ok）；rejected_503 / other_err 分列（503=可预测可重试）
  单调性：1.1 点的 503 份额须 ≥ 0.9 点
  preemptions 计数器 delta（p02_common 纪律：精确 _total 族名、排 _created）
  waiting/running 深度峰值（/metrics gauge 轮询）

用法: p1_batch2_openloop.py --port 19702 --arm-key ADMQ8 --fixture p4k --server-pid P
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gen_fixtures import make_prompt  # noqa: E402
from p02_common import parse_prometheus, counter_total  # noqa: E402

STAGING = os.path.join(NEXTGEN, "raw", "staging")
PARAMS = {
    "p4k": {"prompt_tokens": 4096, "max_tokens": 256, "warmup_s": 30, "measure_s": 120,
            "min_completed": 30, "max_test_s": 300, "closed_reps": 2},
    "p32k": {"prompt_tokens": 32768, "max_tokens": 256, "warmup_s": 60, "measure_s": 240,
             "min_completed": 12, "max_test_s": 900, "closed_reps": 2},
}
RATIOS = (0.9, 1.1)
PREEMPT_FAMILIES = ("vllm:preemption", "vllm:preemption_recycle")


def stream_once(api: str, pload: dict, timeout: int) -> dict:
    req = urllib.request.Request(api + "/chat/completions",
                                 data=json.dumps(pload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first = None
    n_tok = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                if line[6:] == "[DONE]":
                    break
                obj = json.loads(line[6:])
                d = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                if d:
                    n_tok += 1
                    if first is None:
                        first = time.monotonic()
        wall = time.monotonic() - t0
        if first is None or n_tok < 2:
            return {"ok": False, "err": "insufficient_tokens", "http": 200,
                    "ttft": None, "tpot": None}
        ttft = first - t0
        return {"ok": True, "err": None, "http": 200,
                "ttft": round(ttft, 4), "tpot": round((wall - ttft) / (n_tok - 1), 4)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "err": f"HTTP{e.code}", "http": e.code,
                "ttft": None, "tpot": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": str(e)[:120], "http": None,
                "ttft": None, "tpot": None}


def metrics_snapshot(base: str) -> dict:
    try:
        with urllib.request.urlopen(base + "/metrics", timeout=5) as r:
            body = r.read().decode()
    except Exception:  # noqa: BLE001
        return {}
    return parse_prometheus(body)


def preempt_sum(m: dict) -> float:
    tot = 0.0
    for fam in PREEMPT_FAMILIES:
        v = counter_total(m, fam)
        if v is not None:
            tot += v
    return tot


class MetricsPoller(threading.Thread):
    def __init__(self, base: str):
        super().__init__(daemon=True)
        self.base = base
        self.stop_flag = False
        self.waiting_max = 0.0
        self.running_max = 0.0
        self.preempt_first: float | None = None
        self.preempt_last: float | None = None

    def run(self) -> None:
        while not self.stop_flag:
            m = metrics_snapshot(self.base)
            if m:
                w = m.get("vllm:num_requests_waiting")
                r = m.get("vllm:num_requests_running")
                if w is not None:
                    self.waiting_max = max(self.waiting_max, w)
                if r is not None:
                    self.running_max = max(self.running_max, r)
                p = preempt_sum(m)
                if p is not None:
                    if self.preempt_first is None:
                        self.preempt_first = p
                    self.preempt_last = p
            time.sleep(2)


def closed_loop(api: str, ptext: str, mt: int, conc: int, reps: int, salt0: str,
                timeout: int) -> list:
    aggs = []
    for rep in range(reps):
        results: list = []
        lock = threading.Lock()
        barrier = threading.Barrier(conc)

        def synced(i: int) -> None:
            pload = {"model": "qwen3.8-27b", "temperature": 0.7, "seed": 1000 + i,
                     "chat_template_kwargs": {"enable_thinking": False},
                     "messages": [{"role": "user", "content": ptext}],
                     "max_tokens": mt, "stream": True,
                     "cache_salt": f"{salt0}-cl-c{conc}-r{rep}-{i}"}
            barrier.wait()
            res = stream_once(api, pload, timeout)
            with lock:
                results.append(res)

        threads = [threading.Thread(target=synced, args=(i,), daemon=True)
                   for i in range(conc)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout + 60)
        oks = [r for r in results if r["ok"]]
        aggs.append({"rep": rep, "ok": len(oks), "fail": len(results) - len(oks),
                     "ttfts": [r["ttft"] for r in oks],
                     "tpot_mean": (round(statistics.mean(r["tpot"] for r in oks), 4)
                                   if oks else None)})
        time.sleep(2)
    return aggs


def saturation_est(cl: dict, mt: int) -> float:
    best = 0.0
    for conc, reps in cl.items():
        for r in reps:
            if r["ok"]:
                est_wall = max(r["ttfts"]) + (r["tpot_mean"] or 0) * mt
                if est_wall > 0:
                    best = max(best, r["ok"] / est_wall)
    return best


def open_point(api: str, ptext: str, mt: int, rate: float, prm: dict, tag: str,
               poller: MetricsPoller) -> dict:
    rng = __import__("random").Random(hash(tag) & 0xFFFF)
    recs: list = []
    lock = threading.Lock()
    sent = {"n": 0}
    t_end = time.time() + prm["warmup_s"] + prm["measure_s"]
    hard_end = time.time() + prm["max_test_s"]

    def gen() -> None:
        timeout = max(60, prm["measure_s"] // 2 + 60)
        while time.time() < t_end and time.time() < hard_end:
            with lock:
                sent["n"] += 1
                i = sent["n"]
            pload = {"model": "qwen3.8-27b", "temperature": 0.7, "seed": i % 1000,
                     "chat_template_kwargs": {"enable_thinking": False},
                     "messages": [{"role": "user", "content": ptext}],
                     "max_tokens": mt, "stream": True,
                     "cache_salt": f"b2-{tag}-{i}"}

            def go(pload=pload, i=i) -> None:
                res = stream_once(api, pload, timeout)
                with lock:
                    recs.append({"i": i, **res})

            threading.Thread(target=go, daemon=True).start()
            time.sleep(rng.expovariate(rate))

    threading.Thread(target=gen, daemon=True).start()
    while time.time() < t_end + prm["measure_s"] and threading.active_count() > 1:
        time.sleep(5)
        if time.time() > hard_end + 600:
            break
    # 统计：warmup 段计入但 served 分位按 measure 段？——Screen 级全段合并（记 note）
    served = sorted(r["ttft"] for r in recs if r["ok"] and r["ttft"] is not None)

    def pct(a: list, p: float):
        return round(a[min(len(a) - 1, int(len(a) * p))], 3) if a else None

    rej503 = sum(1 for r in recs if r.get("http") == 503)
    other_err = sum(1 for r in recs if not r["ok"] and r.get("http") != 503)
    return {
        "tag": tag, "arrival_rate": round(rate, 4),
        "sent": len(recs), "served_ok": len(served),
        "rejected_503": rej503, "other_err": other_err,
        "rejection_share": round((rej503 + other_err) / len(recs), 4) if recs else None,
        "ttft_p50": pct(served, 0.50), "ttft_p95": pct(served, 0.95),
        "ttft_p99": pct(served, 0.99),
        "tpot_mean": (round(statistics.mean(r["tpot"] for r in recs
                                            if r["ok"] and r["tpot"]), 4)
                      if any(r["ok"] for r in recs) else None),
        "waiting_max": poller.waiting_max, "running_max": poller.running_max,
        "preemptions_delta": ((poller.preempt_last - poller.preempt_first)
                              if poller.preempt_first is not None
                              and poller.preempt_last is not None else None),
        "note": "warmup+measure 全段合并（Screen 级）",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=19702)
    ap.add_argument("--arm-key", required=True)
    ap.add_argument("--fixture", choices=list(PARAMS), required=True)
    ap.add_argument("--server-pid", type=int)
    args = ap.parse_args()
    api = f"http://127.0.0.1:{args.port}/v1"
    base = api.rsplit("/v1", 1)[0]
    prm = PARAMS[args.fixture]
    ptext = make_prompt(prm["prompt_tokens"])
    doc: dict = {"arm": args.arm_key, "fixture": args.fixture, "params": prm,
                 "ts": time.strftime("%F %T")}

    poller = MetricsPoller(base)
    poller.start()
    cl: dict = {}
    for conc in (1, 2, 4, 8):
        cl[str(conc)] = closed_loop(api, ptext, prm["max_tokens"], conc,
                                    prm["closed_reps"], f"b2-{args.arm_key.lower()}",
                                    max(120, prm["max_test_s"] // 3))
        print(json.dumps({"closed": conc, "ok": sum(r["ok"] for r in cl[str(conc)]),
                          "fail": sum(r["fail"] for r in cl[str(conc)])}), flush=True)
    sat = saturation_est(cl, prm["max_tokens"])
    doc["closed_loop"] = cl
    doc["saturation_rate_est"] = round(sat, 4)

    points = []
    pf, pl = poller.preempt_first, poller.preempt_last  # closed 段计入基线
    doc["closed_preemptions_delta"] = (pl - pf) if pf is not None and pl is not None else None
    poller.waiting_max = poller.running_max = 0.0
    for ratio in RATIOS:
        poller.preempt_first = poller.preempt_last = None
        pt = open_point(api, ptext, prm["max_tokens"], sat * ratio, prm,
                        f"{args.arm_key.lower()}-{args.fixture}-r{ratio}", poller)
        points.append(pt)
        print(json.dumps({k: pt[k] for k in ("arrival_rate", "served_ok",
                                             "rejected_503", "ttft_p95")}), flush=True)
    poller.stop_flag = True
    doc["open_points"] = points
    doc["monotonic_503"] = (points[0].get("rejection_share") is not None
                            and points[1].get("rejection_share") is not None
                            and points[1]["rejection_share"] >= points[0]["rejection_share"])

    dest = os.path.join(STAGING, "P02-SCREEN",
                        f"p1-batch2-{args.arm_key.lower()}-openloop-{args.fixture}.json")
    json.dump(doc, open(dest, "w"), indent=1, ensure_ascii=False)
    print(f"written {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

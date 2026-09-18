#!/usr/bin/env python3
"""P5 吞吐-延迟双曲线（SLO_UNDECIDED 义务）。

阶段1 closed-loop：C∈{1,2,4,8} ×3 reps（并发闭环）→ 近似饱和点。
阶段2 open-loop：Poisson 到达，rate = 饱和比 × closed-loop 最大达成速率；
  D565：warmup 120s / measure 300s / min 60 完成 / max 900s
  P220K：warmup 60s / measure 900s / min 20 / max 3600s（A-X profile 用）
输出：arrival/achieved、TTFT P50/P95/P99、TPOT、错误、样本不足→P99=INSUFFICIENT_SAMPLES。
用法: p5_openloop.py --api URL --fixture d565 --out DIR [--phase both]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import random
import statistics
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_fixtures import make_prompt  # noqa: E402

PARAMS = {
    "d565": {"prompt_tokens": 565, "max_tokens": 256, "warmup_s": 120, "measure_s": 300,
             "min_completed": 60, "max_test_s": 900},
    "p220k": {"prompt_tokens": 220000, "max_tokens": 128, "warmup_s": 60, "measure_s": 900,
              "min_completed": 20, "max_test_s": 3600},
}
SAT_RATIOS = (0.25, 0.50, 0.75, 0.90, 1.10)


def stream_once(api, payload, timeout=1200):
    """返回 (ttft_s, tpot_s, ok, err)。逐 token 时间戳在客户端测。"""
    req = urllib.request.Request(api + "/chat/completions",
                                 data=json.dumps(payload).encode(),
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
            return None, None, False, "insufficient_tokens"
        ttft = first - t0
        tpot = (wall - ttft) / (n_tok - 1)
        return ttft, tpot, True, None
    except Exception as e:  # noqa: BLE001
        return None, None, False, str(e)[:120]


def closed_loop(api, ptext, mt, conc, reps, salt0):
    aggs = []
    for rep in range(reps):
        results = [None] * conc
        ths = []
        out_q: queue.Queue = queue.Queue()

        def worker(i):
            payload = {"model": "qwen3.8-27b", "temperature": 0.7, "seed": 1000 + i,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "messages": [{"role": "user", "content": ptext}],
                       "max_tokens": mt, "stream": True,
                       "cache_salt": f"{salt0}-cl-c{conc}-r{rep}-{i}"}
            out_q.put(stream_once(api, payload))

        barrier = threading.Barrier(conc)

        def synced(i):
            barrier.wait()
            worker(i)

        for i in range(conc):
            t = threading.Thread(target=synced, args=(i,))
            t.start()
            ths.append(t)
        for t in ths:
            t.join()
        batch = []
        while not out_q.empty():
            batch.append(out_q.get())
        t_start = min(r for r in [b for b in batch if b[2]][:1]) if any(b[2] for b in batch) else None
        oks = [b for b in batch if b[2]]
        if oks:
            # 近似 batch wall：所有线程 join 后总时长（barrier 起点未记录，用最大 ttft+decode）
            wall = max(b[0] + b[1] * (mt * 0.98) for b in oks) if oks else None
            # 简化：聚合=Σtokens/wall —— 此处以 rep 为单位记录 ok 数与延迟分位
            aggs.append({"rep": rep, "ok": len(oks), "fail": len(batch) - len(oks),
                         "ttfts": [round(b[0], 3) for b in oks],
                         "tpots": [round(b[1], 4) for b in oks]})
    return aggs


def open_loop(api, ptext, mt, rate, prm, salt0, tag):
    rng = random.Random(hash(tag) & 0xFFFF)
    measure_end = time.time() + prm["warmup_s"] + prm["measure_s"]
    hard_end = time.time() + prm["max_test_s"]
    recs: list = []
    lock = threading.Lock()
    sent = {"n": 0}
    t_gen = time.time()

    def gen():
        while time.time() < measure_end and time.time() < hard_end:
            with lock:
                sent["n"] += 1
                i = sent["n"]
            payload = {"model": "qwen3.8-27b", "temperature": 0.7, "seed": i % 1000,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "messages": [{"role": "user", "content": ptext}],
                       "max_tokens": mt, "stream": True,
                       "cache_salt": f"{salt0}-ol-{tag}-{i}"}

            def go(payload=payload, i=i):
                ttft, tpot, ok, err = stream_once(api, payload,
                                                  timeout=max(60, prm["measure_s"] // 2))
                with lock:
                    recs.append({"i": i, "t_send": None, "ok": ok, "ttft": ttft,
                                 "tpot": tpot, "err": err})

            threading.Thread(target=go, daemon=True).start()
            # Poisson 间隔
            time.sleep(rng.expovariate(rate))
    threading.Thread(target=gen, daemon=True).start()
    while time.time() < measure_end + prm["measure_s"] and threading.active_count() > 1:
        time.sleep(5)
        if time.time() > hard_end + 600:
            break
    oks = [r for r in recs if r["ok"]]
    dur = prm["measure_s"]
    ttfts = sorted(r["ttft"] for r in oks)

    def pct(a, p):
        return round(a[min(len(a) - 1, int(len(a) * p))], 3) if a else None

    achieved = len(oks) / dur
    enough = len(oks) >= prm["min_completed"]
    return {
        "tag": tag, "arrival_rate": round(rate, 4), "achieved_rate": round(achieved, 4),
        "completed": len(oks), "failed": len(recs) - len(oks), "enough_samples": enough,
        "ttft_p50": pct(ttfts, 0.50), "ttft_p95": pct(ttfts, 0.95),
        "ttft_p99": (pct(ttfts, 0.99) if enough else "INSUFFICIENT_SAMPLES"),
        "tpot_mean": (round(statistics.mean(r["tpot"] for r in oks), 4) if oks else None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--fixture", choices=list(PARAMS), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--phase", choices=["closed", "open", "both"], default="both")
    ap.add_argument("--max-rate", type=float, default=None,
                    help="闭环饱和速率若已知可显式给（跳过闭环）")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    prm = PARAMS[args.fixture]
    ptext = make_prompt(prm["prompt_tokens"])
    doc = {"fixture": args.fixture, "params": prm}
    sat_rate = args.max_rate
    if args.phase in ("closed", "both") and sat_rate is None:
        cl = {}
        for conc in (1, 2, 4, 8):
            cl[str(conc)] = closed_loop(args.api, ptext, prm["max_tokens"], conc, 3,
                                        f"p5ol-{args.fixture}")
            print(json.dumps({"closed": conc,
                              "ok": sum(r["ok"] for r in cl[str(conc)]),
                              "fail": sum(r["fail"] for r in cl[str(conc)])}), flush=True)
        doc["closed_loop"] = cl
        json.dump(doc, open(os.path.join(args.out, f"curves-{args.fixture}.json"), "w"),
                  indent=1, ensure_ascii=False)
        # 近似饱和：C8 的 ok 平均完成速率（3 reps 平均时长估）
        best = 0.0
        for conc, reps in cl.items():
            for r in reps:
                if r["ok"]:
                    est_wall = max(r["ttfts"]) + statistics.mean(r["tpots"]) * prm["max_tokens"]
                    best = max(best, r["ok"] / est_wall)
        sat_rate = best
        doc["saturation_rate_est"] = round(sat_rate, 4)
        print(json.dumps({"saturation_est": round(sat_rate, 4)}), flush=True)
    if args.phase in ("open", "both"):
        ol = []
        for ratio in SAT_RATIOS:
            rate = sat_rate * ratio
            res = open_loop(args.api, ptext, prm["max_tokens"], rate, prm,
                            f"p5ol-{args.fixture}", f"r{int(ratio*100)}")
            ol.append(res)
            print(json.dumps(res, ensure_ascii=False), flush=True)
            json.dump({**doc, "open_loop": ol},
                      open(os.path.join(args.out, f"curves-{args.fixture}.json"), "w"),
                      indent=1, ensure_ascii=False)
            time.sleep(20)
        doc["open_loop"] = ol
    json.dump(doc, open(os.path.join(args.out, f"curves-{args.fixture}.json"), "w"),
              indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

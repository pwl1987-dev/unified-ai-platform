#!/usr/bin/env python3
"""Phase 03 P0B.4/§9.1 — churn 稳态画像（retention A/B 首跑，Screen 级）。

gates-phase03 churn_and_isolation.churn_load：
  持续 Poisson 到达 + 混合长度（P4K 主体 + P32K 周期插入）+ 多租户共享前缀底座
  （4 租户 × 2K token 基座 + 每请求唯一尾 → 前缀缓存压力/驱逐 churn）
稳态指标：TTFT 时间序列（warm 命中随驱逐衰减形态）、prefix 命中/查询计数器、
  KV 峰、evictions/preemptions、503/err。
A/B：RETDEF（retention 默认）vs RET1024（--retention 1024）同形对照——Phase 02
batch2 的 6.2× 存活观察 → 本测稳态净效应（Screen 级 1 boot/臂，不冒进 Qualify）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
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
from p02_screen import boot_cmd, parse_capacity, stop  # noqa: E402

STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19702

RATE_P4K = 1.2          # rps，主体负载（P4K sat_est 量级之下）
P32K_EVERY_S = 45       # 每 45s 插入一个 P32K 长请求
DURATION_S = 600        # 稳态窗 10min
WARMUP_S = 60
TENANT_BASE_TOKENS = 2048
TENANTS = 4


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
                        first = time.monotonic() - t0
        return {"ok": True, "ttft": first, "tok": n_tok}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": repr(e)[:120]}


def metrics_snapshot(base: str) -> dict:
    try:
        with urllib.request.urlopen(base + "/metrics", timeout=10) as r:
            return parse_prometheus(r.read().decode())
    except Exception:  # noqa: BLE001
        return {}


def prefix_counters(m: dict) -> dict:
    out = {}
    for k in m:
        if "prefix_cache" in k and k.endswith("_total"):
            out[k] = counter_total(k, m)
    return out


class Sampler(threading.Thread):
    def __init__(self, base: str):
        super().__init__(daemon=True)
        self.base, self.samples, self.stop_flag = base, [], False

    def run(self):
        while not self.stop_flag:
            m = metrics_snapshot(self.base)
            gpu_kv = 0
            for k in m:
                if "gpu_prefix_cache" in k or ("kv_cache" in k and "usage" in k):
                    try:
                        gpu_kv = max(gpu_kv, float(m[k]))
                    except (TypeError, ValueError):
                        pass
            self.samples.append({"t": time.time(), "kv_usage": gpu_kv,
                                 "prefix": prefix_counters(m)})
            time.sleep(5)


def run_churn(api: str, base: str, tag: str) -> dict:
    rng = random.Random(20260921)          # churn 负载种子冻结（与 needle seeds 无关）
    tenant_bases = {i: make_prompt(TENANT_BASE_TOKENS) + f"\n租户{i}基座。" for i in range(TENANTS)}
    tail_pool = make_prompt(2048)
    tail_lines = tail_pool.split("\n")
    sampler = Sampler(base)
    sampler.start()
    results = []
    t_end = time.monotonic() + WARMUP_S + DURATION_S
    t_next32 = time.monotonic() + 30
    t_next = time.monotonic()
    while time.monotonic() < t_end:
        now = time.monotonic()
        long_req = False
        if now >= t_next32:
            t_next32 = now + P32K_EVERY_S
            long_req = True
            wait = 0.0
        else:
            if now < t_next:
                time.sleep(min(0.2, max(0.0, t_next - now)))
                continue
            t_next = now + rng.expovariate(RATE_P4K)
        if long_req:
            prompt = make_prompt(32768)
            mt = 128
        else:
            tn = rng.randrange(TENANTS)
            uniq_tail = "\n".join(rng.sample(tail_lines, 24)) + f"\n唯一尾 {rng.randrange(1<<30)}"
            prompt = tenant_bases[tn] + "\n" + uniq_tail
            mt = 64
        pload = {"model": "qwen", "messages": [{"role": "user", "content": prompt}],
                 "max_tokens": mt, "temperature": 0, "stream": True}
        res = stream_once(api, pload, 600)
        res["t"] = time.time()
        res["long"] = long_req
        results.append(res)
    sampler.stop_flag = True
    sampler.join(timeout=10)
    ok = [r for r in results if r.get("ok")]
    ttfts = sorted(r["ttft"] for r in ok if r.get("ttft") is not None)
    short = [r for r in ok if not r["long"] and r.get("ttft") is not None]
    short.sort(key=lambda r: r["t"])
    half = len(short) // 2
    def p(a, q):
        return a[min(len(a) - 1, int(q * len(a)))] if a else None
    # prefix 命中变化率（首末样本差）
    pf = sampler.samples[0]["prefix"] if sampler.samples else {}
    pl = sampler.samples[-1]["prefix"] if sampler.samples else {}
    return {
        "tag": tag, "requests": len(results), "ok": len(ok),
        "err": len(results) - len(ok),
        "ttft_p50": p(ttfts, .5), "ttft_p95": p(ttfts, .95),
        "short_ttft_firsthalf_p50": p([r["ttft"] for r in short[:half]], .5),
        "short_ttft_secondhalf_p50": p([r["ttft"] for r in short[half:]], .5),
        "kv_usage_peak": max((s["kv_usage"] for s in sampler.samples), default=None),
        "prefix_first": pf, "prefix_last": pl,
        "prefix_delta": {k: (pl.get(k, 0) - pf.get(k, 0)) for k in set(pf) | set(pl)},
        "sampler_n": len(sampler.samples),
        "raw_results_tail": results[-40:],
    }


L32 = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
       "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True}
ARMS = {"RETDEF": {"retention": None}, "RET1024": {"retention": 1024}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="RETDEF,RET1024")
    args = ap.parse_args()
    report_path = os.path.join(STAGING, "PH3-P0B", "churn-report.json")
    doc = json.load(open(report_path)) if os.path.exists(report_path) else {"arms": {}}
    for key in args.arms.split(","):
        if key in doc["arms"] and doc["arms"][key].get("done"):
            continue
        b = dict(L32)
        if ARMS[key]["retention"]:
            b["retention"] = ARMS[key]["retention"]
        arm_wrap = {"key": f"CHURN-{key}", "boot": b}
        cmd, tag = boot_cmd(arm_wrap, PORT, "B01")
        print(f"[{key}] booting", flush=True)
        subprocess.run(["bash", "-c", cmd], timeout=2400)
        log = os.path.join("/data/sandbox/nextgen-20260917", f"log-{tag}")
        pgid = pid = None
        for f in ("server.pgid", "server.pid"):
            p = os.path.join(log, f)
            if os.path.exists(p):
                v = int(open(p).read().strip())
                if "pgid" in f:
                    pgid = v
                else:
                    pid = v
        if pgid is None:
            doc["arms"][key] = {"done": False, "error": "BOOT_FAIL"}
            json.dump(doc, open(report_path, "w"), indent=1, ensure_ascii=False)
            continue
        time.sleep(20)   # 健康 stabilise
        r = run_churn(f"http://127.0.0.1:{PORT}/v1", f"http://127.0.0.1:{PORT}", key)
        r["done"] = True
        r["capacity"] = parse_capacity(log)
        doc["arms"][key] = r
        json.dump(doc, open(report_path, "w"), indent=1, ensure_ascii=False)
        stop(pgid)
        time.sleep(5)
    print(json.dumps({k: {"done": v.get("done"),
                          "ttft_p50": v.get("ttft_p50"),
                          "hit_delta": v.get("prefix_delta")}
                      for k, v in doc["arms"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

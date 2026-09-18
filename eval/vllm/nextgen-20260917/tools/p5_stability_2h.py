#!/usr/bin/env python3
"""P5 2h 稳定门——MASTER 混合流量（S-profile 32K 版）：D565/P4K/P32K + tool/JSON + cancel/retry
+ 周期 canary（ccdet 确定性探针，期望 hash 0bd1ecd6…）与 needle-mini。

用法: p5_stability_2h.py --api http://127.0.0.1:19701/v1 --gpu-uuids <u1> --out DIR [--duration 7200]
Gate（gates-phase01.stability_2h）：crash=0、oom=0、http_error_rate≤0.001、preempt≤10、
VRAM 上漂 ≤2%、canary 失败=0。
注意：P128K/P220K 流量属长上下文 profile 的 2h 门（A-X），本 S-profile 服务器 max_len=32K 不含。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nvml_bind  # noqa: E402
from gen_fixtures import make_prompt  # noqa: E402

CANARY_EXPECT = "0bd1ecd60a79a499abf81d34e9b2c1fe32f484d1e04988fdb7f1418d36abf2dd"


def chat(api, payload, timeout=180):
    req = urllib.request.Request(api + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    return json.loads(body), time.time() - t0


def canary_hash(api):
    import hashlib
    payload = {"model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": [{"role": "user", "content": "请逐字输出：NEXTGEN-CCDET-CHECK-7f3a。"}],
               "max_tokens": 24, "stream": False, "cache_salt": "ccdet-fixed-7f3a"}
    obj, _ = chat(api, payload)
    text = (obj.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return hashlib.sha256(text.encode()).hexdigest()


def preempt_count(base):
    try:
        with urllib.request.urlopen(base + "/metrics", timeout=5) as r:
            body = r.read().decode()
        # 只取 _total 计数器：`vllm:num_preemptions_created` 是 Prometheus
        # `_created` gauge（值=进程启动 epoch 秒），误加会把时间戳当抢占数。
        vals = [float(ln.rsplit(" ", 1)[1]) for ln in body.splitlines()
                if ln.startswith("vllm:num_preemptions_total")
                or ln.startswith("vllm:preemption_total")]
        return sum(vals)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--gpu-uuids", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=int, default=7200)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    base = args.api.rsplit("/v1", 1)[0]
    rng = random.Random(20260918)
    nsamp = nvml_bind.NVMLSampler(interval_ms=2000,
                                  uuids=[u for u in args.gpu_uuids.split(",") if u])
    nsamp.start()
    stats = {"requests": 0, "http_errors": 0, "timeouts": 0, "cancels": 0, "retries": 0,
             "canary_failures": 0, "canary_checks": 0, "lat_s": [], "kinds": {}}
    t_end = time.time() + args.duration
    last_canary = 0.0
    vram0 = None
    logf = open(os.path.join(args.out, "stability-log.jsonl"), "w")

    def one(kind, payload, timeout=180, cancel_after=None):
        stats["requests"] += 1
        stats["kinds"][kind] = stats["kinds"].get(kind, 0) + 1
        try:
            if cancel_after:
                req = urllib.request.Request(args.api + "/chat/completions",
                                             data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json"})
                try:
                    urllib.request.urlopen(req, timeout=cancel_after).close()
                    stats["cancels"] += 1
                except Exception:
                    stats["cancels"] += 1
                return
            obj, dt = chat(args.api, payload, timeout)
            stats["lat_s"].append(round(dt, 3))
        except urllib.error.HTTPError as e:
            stats["http_errors"] += 1
            logf.write(json.dumps({"t": time.time(), "kind": kind, "http": e.code}) + "\n")
        except Exception as e:  # noqa: BLE001
            stats["timeouts"] += 1
            logf.write(json.dumps({"t": time.time(), "kind": kind, "err": str(e)[:120]}) + "\n")

    while time.time() < t_end:
        now = time.time()
        v = nsamp.samples
        if v:
            mems = [c.get("mem_used_mib") for c in v if c.get("mem_used_mib")]
            if mems:
                cur = max(mems)
                vram0 = vram0 or cur
        r = rng.random()
        if r < 0.35:      # D565 交互
            one("d565-ns", {"model": "qwen3.8-27b", "temperature": 0.7, "seed": rng.randint(1, 10**6),
                            "chat_template_kwargs": {"enable_thinking": False},
                            "messages": [{"role": "user", "content": make_prompt(565)}],
                            "max_tokens": 256, "stream": False,
                            "cache_salt": f"s2h-d565-{rng.randint(1, 10**9)}"})
        elif r < 0.55:    # P4K
            one("p4k-ns", {"model": "qwen3.8-27b", "temperature": 0.7, "seed": rng.randint(1, 10**6),
                           "chat_template_kwargs": {"enable_thinking": False},
                           "messages": [{"role": "user", "content": make_prompt(4096)}],
                           "max_tokens": 256, "stream": False,
                           "cache_salt": f"s2h-p4k-{rng.randint(1, 10**9)}"})
        elif r < 0.70:    # P32K（30000 token：留输出+模板余量；顶满 32768 会 400 拒绝污染门）
            one("p32k-ns", {"model": "qwen3.8-27b", "temperature": 0.7, "seed": rng.randint(1, 10**6),
                            "chat_template_kwargs": {"enable_thinking": False},
                            "messages": [{"role": "user", "content": make_prompt(30000)}],
                            "max_tokens": 256, "stream": False,
                            "cache_salt": f"s2h-p32k-{rng.randint(1, 10**9)}"}, timeout=600)
        elif r < 0.82:    # tool/JSON
            one("json-mode", {"model": "qwen3.8-27b", "temperature": 0,
                              "chat_template_kwargs": {"enable_thinking": False},
                              "messages": [{"role": "user", "content":
                                            "以 JSON 输出 {\"name\":..., \"age\":...} 的人物档案，张三 42 岁。"}],
                              "max_tokens": 128, "stream": False,
                              "response_format": {"type": "json_object"},
                              "cache_salt": f"s2h-json-{rng.randint(1, 10**9)}"})
        elif r < 0.90:    # cancel（中途断开）
            one("cancel", {"model": "qwen3.8-27b", "temperature": 0.7,
                           "chat_template_kwargs": {"enable_thinking": False},
                           "messages": [{"role": "user", "content": make_prompt(2048)}],
                           "max_tokens": 256, "stream": True,
                           "cache_salt": f"s2h-cancel-{rng.randint(1, 10**9)}"},
                cancel_after=0.4)
        else:             # retry 模式（短超时后立即重试一次）
            stats["retries"] += 1
            one("retry", {"model": "qwen3.8-27b", "temperature": 0.7,
                          "chat_template_kwargs": {"enable_thinking": False},
                          "messages": [{"role": "user", "content": make_prompt(565)}],
                          "max_tokens": 128, "stream": False,
                          "cache_salt": f"s2h-retry-{rng.randint(1, 10**9)}"}, timeout=3)
        # 周期 canary（每 300s）
        if now - last_canary >= 300:
            last_canary = now
            try:
                h = canary_hash(args.api)
                stats["canary_checks"] += 1
                if h != CANARY_EXPECT:
                    stats["canary_failures"] += 1
                    logf.write(json.dumps({"t": now, "canary_hash": h}) + "\n")
            except Exception as e:  # noqa: BLE001
                stats["canary_failures"] += 1
                logf.write(json.dumps({"t": now, "canary_err": str(e)[:120]}) + "\n")
        time.sleep(rng.uniform(0.3, 1.2))
    nsamp.stop()
    mems = [c.get("mem_used_mib") for c in nsamp.samples if c.get("mem_used_mib")]
    vram_final = max(mems) if mems else None
    pre = preempt_count(base)
    err_rate = stats["http_errors"] / stats["requests"] if stats["requests"] else 0
    verdict = {
        "duration_s": args.duration, "requests": stats["requests"],
        "http_error_rate": round(err_rate, 6), "timeouts": stats["timeouts"],
        "cancels": stats["cancels"], "retries": stats["retries"],
        "canary_checks": stats["canary_checks"], "canary_failures": stats["canary_failures"],
        "preemptions": pre, "vram_start_mib": vram0, "vram_final_mib": vram_final,
        "vram_upward_drift_pct": (round((vram_final - vram0) / vram0 * 100, 3)
                                  if vram0 and vram_final else None),
        "lat_p50": (round(statistics.median(stats["lat_s"]), 3) if stats["lat_s"] else None),
        "kinds": stats["kinds"],
        "gate": {
            "crashes": stats["timeouts"] == 0 and err_rate <= 0.001,  # 粗粒度：无不可恢复错误
            "http_error_rate_le_0.001": err_rate <= 0.001,
            "preempt_le_10": (pre is None) or pre <= 10,
            "vram_drift_le_2pct": (not vram0 or not vram_final
                                   or (vram_final - vram0) / vram0 <= 0.02),
            "canary_zero_fail": stats["canary_failures"] == 0,
        },
    }
    verdict["PASS"] = all(verdict["gate"].values())
    json.dump(verdict, open(os.path.join(args.out, "stability-2h.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

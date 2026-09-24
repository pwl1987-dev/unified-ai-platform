#!/usr/bin/env python3
"""ph5_workload.py — Phase 05 多会话/混合/prefix-sticky/failover 场景编排器。

场景（gates-phase05 screen_p1.cells）：
  multi    通用并行会话：--sess sid:fixture:maxtok[:saltkey]（可多次）→ 每会话一个
           bench_nextgen 子进程（C1 + --session-id），聚合 per-session 指标 + fairness（Jain）
  sticky   同会话多轮（--turns N）+ 并行新会话（--parallel-new K）：原生 HTTP 递增对话，
           逐轮 TTFT（prefix cache 命中→轮间下降）；router 路由日志核验粘滞；
           backend /metrics prefix_cache 计数器 before/after 差
  failover 持续 D565 流量中途 SIGTERM 一个自有 backend（--kill-pid）：客户端可见错误数、
           FAILOVER_REBIND 时延（route log）、前后 goodput

统一输出 <out-dir>/cell-summary.json；子进程 evidence 各自落 <out-dir>/<sid>/。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "bench_nextgen.py")
PY = sys.executable


def jain(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sum(xs)
    return (s * s) / (len(xs) * sum(x * x for x in xs)) if s else 0.0


def run_bench(api: str, eid: str, sess_spec: str, out_dir: str, common: list[str]) -> int:
    parts = sess_spec.split(":")
    sid, fixture, maxtok = parts[0], parts[1], parts[2]
    salt = parts[3] if len(parts) > 3 else f"{eid}-{sid}"
    cmd = [PY, BENCH, "--api", api, "--experiment-id", f"{eid}-{sid}",
           "--fixture", fixture, "--mode", "fixed-output", "--concurrency", "1",
           "--max-tokens", maxtok, "--session-id", sid, "--salt-key", salt,
           "--out-dir", os.path.join(out_dir, sid)] + common
    return subprocess.run(cmd).returncode


def scenario_multi(args) -> int:
    t0 = time.time()
    procs = []
    for spec in args.sess:
        sid = spec.split(":")[0]
        cmd = [PY, BENCH, "--api", args.api, "--experiment-id", f"{args.experiment_id}-{sid}",
               "--fixture", spec.split(":")[1], "--mode", "fixed-output", "--concurrency", "1",
               "--max-tokens", spec.split(":")[2], "--session-id", sid,
               "--salt-key", (spec.split(":")[3] if len(spec.split(":")) > 3 else f"{args.experiment_id}-{sid}"),
               "--out-dir", os.path.join(args.out_dir, sid)] + args.bench_extra
        procs.append((sid, spec, subprocess.Popen(cmd)))
    results = {}
    for sid, spec, p in procs:
        p.wait()
        mp = os.path.join(args.out_dir, sid, "metrics.json")
        m = json.load(open(mp)) if os.path.exists(mp) else {}
        pr = m.get("per_request") or []
        ttfts = [r.get("ttft_s") for r in pr if r.get("ok") and r.get("ttft_s") is not None]
        tpots = [r.get("tpot_s") for r in pr if r.get("ok") and r.get("tpot_s") is not None]
        goodput = (m.get("requests_ok") or 0) / ((m.get("aggregate") or {}).get("batch_wall_s") or 1e-9)
        results[sid] = {
            "fixture": spec.split(":")[1], "rc": p.returncode,
            "requests_ok": m.get("requests_ok"), "requests_total": m.get("requests_total"),
            "http_errors": m.get("http_errors"),
            "ttft_p50": sorted(ttfts)[len(ttfts) // 2] if ttfts else None,
            "ttft_max": max(ttfts) if ttfts else None,
            "tpot_med": sorted(tpots)[len(tpots) // 2] if tpots else None,
            "sum_output_tokens": (m.get("aggregate") or {}).get("sum_output_tokens"),
            "batch_wall_s": (m.get("aggregate") or {}).get("batch_wall_s"),
            "goodput_rps": round(goodput, 4),
            "tok_s": round(((m.get("aggregate") or {}).get("sum_output_tokens") or 0) /
                           ((m.get("aggregate") or {}).get("batch_wall_s") or 1e-9), 3),
        }
    walls = [r["batch_wall_s"] or 0 for r in results.values()]
    summary = {
        "scenario": "multi", "experiment_id": args.experiment_id, "api": args.api,
        "wall_s": round(time.time() - t0, 2),
        "sessions": results,
        "aggregate_tok_s": round(sum(r["sum_output_tokens"] or 0 for r in results.values()) /
                                 (max(walls) if walls else 1e-9), 3),
        "fairness_jain_goodput": round(jain([r["goodput_rps"] or 0 for r in results.values()]), 4),
        "per_session_p95_ttft": max((r["ttft_max"] or 0) for r in results.values()),
    }
    json.dump(summary, open(os.path.join(args.out_dir, "cell-summary.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False)[:1200])
    return 0 if all(r["rc"] == 0 for r in results.values()) else 1


async def _one_chat(api: str, body: dict, sid: str, timeout: float):
    import urllib.request
    t0 = time.perf_counter()
    req = urllib.request.Request(api + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Session-Id": sid})
    resp = urllib.request.urlopen(req, timeout=timeout)
    first = None
    for line in resp:
        if line.strip():
            first = time.perf_counter()
            break
    data = json.loads(resp.read() or b"{}")
    return {"ttft_s": round(first - t0, 4) if first else None,
            "content": (data.get("choices") or [{}])[0].get("message", {}).get("content", "")}


async def _get(url: str) -> str:
    import urllib.request
    return urllib.request.urlopen(url, timeout=10).read().decode()


def _prefix_counters(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or "prefix_cache" not in line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                out[parts[0]] = float(parts[1])
            except ValueError:
                pass
    return out


async def scenario_sticky(args) -> int:
    filler = ("以下是多轮会话粘滞与前缀缓存验证。会话 {sid} 第 {turn} 轮。"
              "请用一句话确认你看到的轮次编号。背景资料：" + "拓扑赛确定性填充材料。" * 120)
    hist: dict[str, list] = {}
    per_turn = {f"sticky-{i+1}": [] for i in range(args.sticky_sessions)}
    # backend prefix 计数 before（router /backends 找 url）
    backends = json.loads(await _get(args.api.replace("/v1", "/backends")))["backends"]
    before = {b["name"]: _prefix_counters(await _get(b["url"] + "/metrics")) for b in backends}
    # 1) 同会话连续多轮
    for i in range(args.sticky_sessions):
        sid = f"sticky-{i+1}"
        for turn in range(1, args.turns + 1):
            msg = [{"role": "user", "content": filler.format(sid=sid, turn=turn)}]
            body = {"model": "qwen3.8-27b", "messages": hist.get(sid, []) + msg,
                    "max_tokens": 32, "temperature": 0, "seed": 4242}
            r = await _one_chat(args.api, body, sid, args.timeout_s)
            r["turn"] = turn
            per_turn[sid].append(r)
            hist.setdefault(sid, []).extend(msg + [{"role": "assistant", "content": r["content"]}])
            await asyncio.sleep(0.2)
    # 2) 并行新会话（漂移检测）
    new_tasks = []
    for k in range(args.parallel_new):
        sid = f"fresh-{k+1}"
        body = {"model": "qwen3.8-27b",
                "messages": [{"role": "user", "content": filler.format(sid=sid, turn=1)}],
                "max_tokens": 32, "temperature": 0, "seed": 4242}
        new_tasks.append(_one_chat(args.api, body, sid, args.timeout_s))
    new_res = await asyncio.gather(*new_tasks)
    # 3) 粘滞核验：router route log 中 sticky 命中
    routes = [json.loads(l) for l in open(args.route_log)] if os.path.exists(args.route_log) else []
    sess_backends = {}
    for r in routes:
        if r.get("session"):
            sess_backends.setdefault(r["session"], set()).add(r.get("backend"))
    sticky_ok = {sid: len(v) == 1 for sid, v in sess_backends.items() if sid.startswith("sticky-")}
    after = {b["name"]: _prefix_counters(await _get(b["url"] + "/metrics")) for b in backends}
    delta = {n: {k: after[n].get(k, 0) - before[n].get(k, 0) for k in set(before[n]) | set(after[n])}
             for n in after}
    ttft_first = [v[0]["ttft_s"] for v in per_turn.values() if v and v[0]["ttft_s"]]
    ttft_last = [v[-1]["ttft_s"] for v in per_turn.values() if v and v[-1]["ttft_s"]]
    summary = {
        "scenario": "sticky", "experiment_id": args.experiment_id,
        "turns_per_session": args.turns, "sessions": {
            sid: {"ttft_per_turn": [t["ttft_s"] for t in turns]} for sid, turns in per_turn.items()},
        "fresh_sessions_ttft": [r.get("ttft_s") for r in new_res],
        "ttft_first_turn_med": sorted(ttft_first)[len(ttft_first)//2] if ttft_first else None,
        "ttft_last_turn_med": sorted(ttft_last)[len(ttft_last)//2] if ttft_last else None,
        "sticky_binding_ok": all(sticky_ok.values()) if sticky_ok else False,
        "session_backend_map": {k: sorted(v) for k, v in sess_backends.items()},
        "prefix_cache_counter_delta": delta,
    }
    json.dump(summary, open(os.path.join(args.out_dir, "cell-summary.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False)[:1200])
    return 0


def scenario_failover(args) -> int:
    t0 = time.time()
    # 持续流量：顺序短 run 直至 kill 点后仍再跑 3 个 run
    api, eid, od = args.api, args.experiment_id, args.out_dir
    runs, i = [], 0
    kill_at = time.time() + args.kill_after_s

    def one_run(i):
        return subprocess.run([PY, BENCH, "--api", api, "--experiment-id", f"{eid}-fo{i}",
                               "--fixture", "d565", "--mode", "fixed-output", "--concurrency", "1",
                               "--max-tokens", "128", "--session-id", f"fo-{i}",
                               "--salt-key", f"{eid}-fo{i}", "--out-dir", os.path.join(od, f"fo{i}")],
                              capture_output=True, text=True)
    killed = False
    while time.time() < kill_at + 3 * 90 and i < args.max_runs:
        r = one_run(i)
        runs.append(r.returncode)
        if not killed and time.time() >= kill_at:
            os.kill(args.kill_pid, signal.SIGTERM)
            kill_ts = time.time()
            killed = True
        i += 1
    routes = [json.loads(l) for l in open(args.route_log)] if os.path.exists(args.route_log) else []
    rebinds = [r["ts"] for r in routes if r.get("reason") == "FAILOVER_REBIND"]
    summary = {
        "scenario": "failover", "experiment_id": eid, "kill_pid": args.kill_pid,
        "runs_rc": runs, "failed_runs": sum(1 for rc in runs if rc != 0),
        "rebind_count": len(rebinds),
        "wall_s": round(time.time() - t0, 1),
    }
    if killed and rebinds:
        summary["rebind_latency_s"] = round(min(rebinds) - kill_ts, 3)
    json.dump(summary, open(os.path.join(od, "cell-summary.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["multi", "sticky", "failover"], required=True)
    ap.add_argument("--api", required=True, help="router 或直连 backend 的 /v1")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--sess", action="append", default=[],
                    help="multi: sid:fixture:maxtok[:saltkey]")
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--sticky-sessions", type=int, default=2)
    ap.add_argument("--parallel-new", type=int, default=3)
    ap.add_argument("--timeout-s", type=int, default=300)
    ap.add_argument("--route-log", default="/data/sandbox/nextgen-20260917/ph5-router-routes.jsonl")
    ap.add_argument("--kill-pid", type=int)
    ap.add_argument("--kill-after-s", type=float, default=60.0)
    ap.add_argument("--max-runs", type=int, default=12)
    ap.add_argument("--bench-extra", default="", help="透传 bench_nextgen 的额外参数（空格分隔）")
    args = ap.parse_args()
    args.bench_extra = args.bench_extra.split() if args.bench_extra else []
    os.makedirs(args.out_dir, exist_ok=True)
    if args.scenario == "multi":
        return scenario_multi(args)
    if args.scenario == "sticky":
        return asyncio.run(scenario_sticky(args))
    if not args.kill_pid:
        ap.error("failover 需要 --kill-pid（自有 backend PID）")
    return scenario_failover(args)


if __name__ == "__main__":
    raise SystemExit(main())

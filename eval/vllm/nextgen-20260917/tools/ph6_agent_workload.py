#!/usr/bin/env python3
"""ph6_agent_workload.py — Phase 06 Agent 形态负载编排器（gates-phase06 agent_workloads）。

场景：
  mix       F1_MIX：2×AG-SHORT 流 + 1×AG-LONG(p32k) + 1×AG-BATCH(C4×2 波) 并发；
            逐请求事件 events.jsonl；per-role 汇总 cell-summary.json。
  isolation F2_ISOLATION：2×AG-LONG(p128kt, 连续 hogging) + 3×AG-SHORT 常驻 +
            churn 波（每 --churn-interval-s 一个新 short 会话 ×3 轮 ×--churn-waves 波）+
            可选强驱逐（--evict-after-s：router /admin/evict 驱逐 hog-1，随后探测
            release latency=下一 long 请求 TTFT；被逐会话在途请求应收 409 EVICTED）。

负载语义（与 gates-phase06 对齐的机器细节）：
  AG-SHORT：首轮 prompt=make_prompt(512)（d565 冻结语料），上下文逐轮累积（历史+助手输出+轮标记），
            6 轮 × max_tokens 512，轮间隔 1s。
  AG-LONG(p32k)：首轮=make_prompt(32768)，上下文逐轮累积，3 轮 × mt 256，间隔 2s。
  AG-LONG(p128kt)（F2 hog 变体）：每轮一份新"文档"=冻结前缀(make_prompt(130900) 的稳定头部)
            + 轮标记（文档流语义：同 session 同前缀 → prefix-cache 友好；单轮装配 ≤131072），
            连续轮直到场景结束，mt 128。
  AG-BATCH：p4k prompt，C4 并发 ×2 波（波间隔 5s），mt 256。
  全部请求带 X-Session-Id 与 X-Role 头（A/B 两臂传输路径一致；blind router 忽略 X-Role）。

指标（contract fairness_metrics）：per-role requests/ok/completion/ttft p50/p95/max/tpot、
per-session goodput、Jain(fairness)、failure_window_s（short TTFT>bound 最长连续窗）、
evict{release_latency_s, evicted_error_class, inflight_after}、router queue 高水位。
输出：<out-dir>/events.jsonl + cell-summary.json。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/data/repos/qwen3.8-27b-8x4090-stack/inference/vllm/bench")  # 冻结夹具构造
from ulmus_validate import make_prompt  # noqa: E402
from sseparser import SSEParser, extract_content, extract_finish_reason  # noqa: E402

SEED = 4242
BOUND_SHORT_TTFT_S = 5.0            # gates-phase06 F2 hard gate bound


def fixture_prompt(target: int, stable_prefix: bool = True) -> str:
    """冻结语料；stable_prefix=True 时同 target 重复调用返回同一前缀（文档流语义）。"""
    return make_prompt(target)


class Events:
    def __init__(self, out_dir: str):
        self.path = os.path.join(out_dir, "events.jsonl")
        self.fh = open(self.path, "a", buffering=1)
        self.lock = __import__("threading").Lock()

    def emit(self, **kw):
        kw["ts"] = round(time.time(), 4)
        with self.lock:
            self.fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def _chat_stream_sync(api: str, messages: list, sid: str, role: str, max_tokens: int,
                      ev: Events, timeout: float, turn: int) -> dict:
    """阻塞式单请求（跑在线程池）：真 TTFT（首个 content delta）/完成/输出数/错误分类。"""
    body = {"model": "qwen3.8-27b", "messages": messages, "max_tokens": max_tokens,
            "temperature": 0, "seed": SEED, "stream": True,
            "stream_options": {"include_usage": True},
            # 战役标准形制（bench_nextgen 同款）：Qwen3.8 思考模板关闭——
            # ① 与 Phase 02-05 全部认证 cell 同语义；② p128kt 级装配余量依赖它
            # （思考模板 +~45 tok 会使 130945+128 超 131072 恰 1 token → 引擎 400）
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(
        api + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Session-Id": sid, "X-Role": role})
    t0 = time.perf_counter()
    first = None
    ntok = 0
    finish = None
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        parser = SSEParser()
        usage = None
        for line in resp:
            for ev_ in parser.feed(line):
                if ev_["kind"] == "done":
                    continue
                if ev_["kind"] != "data" or ev_.get("malformed"):
                    continue
                obj = ev_["json"]
                c = extract_content(obj)
                if c:
                    if first is None:
                        first = time.perf_counter()
                    ntok += 1
                fr = extract_finish_reason(obj)
                if fr:
                    finish = fr
                if obj.get("usage"):
                    usage = obj["usage"]
        parser.flush()
        # spec decode 一个 chunk 可含多 token：事件数≠token 数；server usage 优先（bench 同款）
        out_tokens = usage.get("completion_tokens") if usage else None
        if out_tokens is None:
            out_tokens = ntok
        ok = finish in ("stop", "length") and out_tokens > 0
        err = None if ok else "OUTPUT_EMPTY" if out_tokens == 0 else f"FINISH_{finish}"
        ttft = round(first - t0, 4) if first else None
        wall = round(time.perf_counter() - t0, 4)
        tpot = round((wall - (first - t0)) / (out_tokens - 1), 4) if first and out_tokens > 1 else None
        rec = dict(sid=sid, role=role, turn=turn, ok=ok, error_class=err, ttft_s=ttft,
                   wall_s=wall, tpot_s=tpot, out_tokens=out_tokens, finish=finish,
                   client_event_count=ntok)
    except urllib.error.HTTPError as e:
        errbody = ""
        try:
            errbody = e.read().decode()[:200]
        except Exception:
            pass
        cls = "EVICTED" if "SESSION_EVICTED" in errbody else (
            "CAPACITY_LIMIT" if "maximum context length" in errbody else
            ("ROUTER_4XX" if 400 <= e.code < 500 else "HTTP_5XX"))
        rec = dict(sid=sid, role=role, turn=turn, ok=False, error_class=cls,
                   http_status=e.code, err_body=errbody,
                   ttft_s=None, wall_s=round(time.perf_counter() - t0, 4),
                   tpot_s=None, out_tokens=0, finish=None)
    except Exception as e:
        cls = "TIMEOUT" if "timed out" in str(e).lower() else "TRANSPORT"
        rec = dict(sid=sid, role=role, turn=turn, ok=False, error_class=cls,
                   err=repr(e)[:120], ttft_s=None,
                   wall_s=round(time.perf_counter() - t0, 4),
                   tpot_s=None, out_tokens=0, finish=None)
    ev.emit(**rec)
    return rec


async def chat_stream(api, messages, sid, role, max_tokens, ev, turn=0, timeout=300.0) -> dict:
    """async 包装：阻塞请求放线程池（并发 persona 不互相阻塞事件循环；计时在线程内）。"""
    return await asyncio.to_thread(_chat_stream_sync, api, messages, sid, role,
                                   max_tokens, ev, timeout, turn)


# ---------------- personas ----------------
async def persona_short(api, sid, ev, turns=6, mt=512, gap=1.0):
    base = fixture_prompt(512)
    turn_mark = "（第 {t} 轮）请继续，用一句话确认轮次。"
    hist: list = [{"role": "user", "content": base}]
    for t in range(1, turns + 1):
        if t > 1:
            hist.append({"role": "user", "content": turn_mark.format(t=t)})
        r = await chat_stream(api, hist, sid, "short", mt, ev, turn=t)
        if not r["ok"]:
            return
        hist.append({"role": "assistant", "content": f"[ack turn {t}]"})
        await asyncio.sleep(gap)


async def persona_long(api, sid, ev, turns=3, mt=256, gap=2.0):
    base = fixture_prompt(32768)
    turn_mark = "（第 {t} 轮）基于以上资料，继续分析并给出下一步。"
    hist: list = [{"role": "user", "content": base}]
    for t in range(1, turns + 1):
        if t > 1:
            hist.append({"role": "user", "content": turn_mark.format(t=t)})
        r = await chat_stream(api, hist, sid, "long", mt, ev, turn=t)
        if not r["ok"]:
            return
        hist.append({"role": "assistant", "content": f"[long ack {t}]"})
        await asyncio.sleep(gap)


async def persona_hog(api, sid, ev, stop_at: float, mt=128, tag="hog"):
    """p128kt 文档流：同冻结前缀逐轮重发（prefix-cache 友好，单轮装配=PH5 认证形制 ≤131072），
    连续轮直到场景墙钟。"""
    base = fixture_prompt(130900)
    t = 0
    while time.time() < stop_at:
        t += 1
        r = await chat_stream(api, [{"role": "user", "content": base}], sid, "long", mt, ev, turn=t)
        if not r["ok"]:
            await asyncio.sleep(1.0)
            continue
        await asyncio.sleep(0.5)


async def persona_batch(api, prefix, ev, conc=4, bursts=2, mt=256, gap=5.0):
    base = fixture_prompt(4096)
    for b in range(1, bursts + 1):
        tasks = []
        for i in range(conc):
            sid = f"{prefix}-b{b}-{i}"
            tasks.append(chat_stream(api, [{"role": "user", "content": base + f"\n（批次 {b} 任务 {i}）"}],
                                     sid, "batch", mt, ev, turn=b))
        await asyncio.gather(*tasks)
        await asyncio.sleep(gap)


async def churn_wave(api, wave, ev, turns=3, mt=512):
    sid = f"churn-{wave}"
    await persona_short(api, sid, ev, turns=turns, mt=mt, gap=0.5)


# ---------------- scenarios ----------------
async def run_mix(args) -> int:
    t0 = time.time()
    ev = Events(args.out_dir)
    ev.emit(scenario="mix", event="START", api=args.api)
    tasks = [
        persona_short(args.api, "short-1", ev),
        persona_short(args.api, "short-2", ev),
        persona_long(args.api, "long-1", ev),
        persona_batch(args.api, "batch", ev),
    ]
    await asyncio.gather(*tasks)
    ev.emit(scenario="mix", event="END", wall_s=round(time.time() - t0, 1))
    summarize(args, t0)
    return 0


async def run_isolation(args) -> int:
    t0 = time.time()
    ev = Events(args.out_dir)
    ev.emit(scenario="isolation", event="START", api=args.api)
    stop_at = t0 + args.duration_s
    hogs = [asyncio.create_task(persona_hog(args.api, "hog-1", ev, stop_at)),
            asyncio.create_task(persona_hog(args.api, "hog-2", ev, stop_at))]
    await asyncio.sleep(min(10.0, args.duration_s * 0.1))   # 让 hog 先占住 TP2（MS2）
    residents = [asyncio.create_task(persona_short(args.api, f"res-{i}", ev, turns=6))
                 for i in range(3)]
    evict_meta = {}
    for w in range(1, args.churn_waves + 1):
        await asyncio.sleep(args.churn_interval_s)
        await churn_wave(args.api, w, ev)
        if args.evict_after_s and not evict_meta and time.time() - t0 >= args.evict_after_s:
            evict_meta = await do_evict(args, ev)
    await asyncio.gather(*residents)
    for h in hogs:
        h.cancel()
    await asyncio.gather(*hogs, return_exceptions=True)
    ev.emit(scenario="isolation", event="END", wall_s=round(time.time() - t0, 1))
    rc = summarize(args, t0, evict=evict_meta)
    # 清场：驱逐后宽限窗内 hog 残余请求若仍在跑已被 cancel；路由 inflight 复核
    def _backends():
        return json.loads(urllib.request.urlopen(
            f"{args.api.rsplit('/v1',1)[0]}/backends", timeout=10).read())["backends"]
    try:
        bks = await asyncio.to_thread(_backends)
        rc["backends_inflight_after"] = {b["name"]: b["inflight"] for b in bks}
        rc["backends_max_inflight"] = {b["name"]: b["max_inflight"] for b in bks}
        json.dump(rc, open(os.path.join(args.out_dir, "cell-summary.json"), "w"),
                  indent=1, ensure_ascii=False)
    except Exception as e:
        rc["backends_check_error"] = repr(e)[:120]
    return 0


async def do_evict(args, ev) -> dict:
    admin = args.api.rsplit("/v1", 1)[0] + "/admin/evict?session=hog-1"

    def _admin():
        t_e = time.perf_counter()
        req = urllib.request.Request(admin, method="POST")
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return resp, round(time.perf_counter() - t_e, 4)
    resp, dt = await asyncio.to_thread(_admin)
    ev.emit(scenario="isolation", event="EVICT", admin_reply=resp, admin_dt_s=dt)
    # 探测：下一 long 请求 TTFT = release latency（从 evict 时刻起算）
    probe_sid = f"probe-{int(time.time())}"
    base = fixture_prompt(130900)
    r = await chat_stream(args.api, [{"role": "user", "content": base + "\n（驱逐后探测）请摘要。"}],
                          probe_sid, "long", 64, ev, turn=1)
    return {"evicted_session": resp.get("evicted"),
            "release_latency_s": r.get("ttft_s"),   # evict→TP2 可服务（含队列）首字节
            "probe_ok": r.get("ok"), "probe_error": r.get("error_class")}


# ---------------- summary ----------------
def pctl(xs: list[float], p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def summarize(args, t0, evict=None) -> dict:
    events = [json.loads(l) for l in open(os.path.join(args.out_dir, "events.jsonl"))]
    reqs = [e for e in events if "sid" in e]
    # 驱逐家族重分类（合同 F2：EVICTED 单列不计失败）：被逐会话在途请求的流中断
    # （FINISH_None）属驱逐因果 → EVICTED_MIDSTREAM（events.jsonl 原始记录不动）
    if evict and evict.get("evicted_session"):
        for e in reqs:
            if (e.get("sid") == evict["evicted_session"]
                    and e.get("error_class") == "FINISH_None"):
                e["error_class"] = "EVICTED_MIDSTREAM"
    roles = {}
    for role in ("short", "long", "batch"):
        rs = [e for e in reqs if e["role"] == role]
        ttfts = [e["ttft_s"] for e in rs if e["ok"] and e["ttft_s"] is not None]
        walls = [e["wall_s"] for e in rs if e["ok"]]
        tpots = [e["tpot_s"] for e in rs if e["ok"] and e.get("tpot_s")]
        roles[role] = {
            "requests": len(rs), "ok": sum(1 for e in rs if e["ok"]),
            "completion_rate": round(sum(1 for e in rs if e["ok"]) / len(rs), 4) if rs else None,
            "ttft_p50": pctl(ttfts, 0.5), "ttft_p95": pctl(ttfts, 0.95),
            "ttft_max": max(ttfts) if ttfts else None,
            "tpot_med": statistics.median(tpots) if tpots else None,
            "sum_output_tokens": sum(e.get("out_tokens") or 0 for e in rs),
            "wall_med": statistics.median(walls) if walls else None,
            "errors": {c: sum(1 for e in rs if e.get("error_class") == c)
                       for c in {e.get("error_class") for e in rs if not e["ok"]}},
        }
    # per-session goodput + Jain；另记全量会话成败账（churn 完成性判据需失败可见）
    sess = {}
    for e in reqs:
        s = sess.setdefault(e["sid"], {"requests": 0, "ok": 0, "tok": 0,
                                       "wall": 0.0, "role": e["role"]})
        s["requests"] += 1
        if e["ok"]:
            s["ok"] += 1
            s["tok"] += e.get("out_tokens") or 0
            s["wall"] += e.get("wall_s") or 0
    for s in sess.values():
        s["goodput_tok_s"] = round(s["tok"] / s["wall"], 4) if s["wall"] else None
    gvals = [s["goodput_tok_s"] for s in sess.values() if s["goodput_tok_s"] is not None]
    jain = ((sum(gvals) ** 2) / (len(gvals) * sum(v * v for v in gvals))
            if gvals else None)
    # 合同 F2 冻结指标 = jain_short_goodput（short 会话子集）；全会话 jain 另列
    gshort = [s["goodput_tok_s"] for s in sess.values()
              if s["role"] == "short" and s["goodput_tok_s"] is not None]
    jain_short = ((sum(gshort) ** 2) / (len(gshort) * sum(v * v for v in gshort))
                  if gshort else None)
    # failure window：short TTFT > bound 的最长连续时间跨度
    shorts = sorted([e for e in reqs if e["role"] == "short" and e["ttft_s"] is not None],
                    key=lambda e: e["ts"])
    worst = None
    run_start = None
    for e in shorts + [{"ts": float("inf"), "ttft_s": 0}]:
        if e["ttft_s"] > BOUND_SHORT_TTFT_S:
            if run_start is None:
                run_start = e["ts"]
        else:
            if run_start is not None:
                w = e["ts"] - run_start
                if worst is None or w > worst:
                    worst = w
                run_start = None
    summary = {
        "scenario": args.scenario, "policy": args.policy, "api": args.api,
        "wall_s": round(time.time() - t0, 1),
        "per_role": roles,
        "per_session": sess,
        "fairness_jain_goodput": round(jain, 4) if jain else None,
        "fairness_jain_short_goodput": round(jain_short, 4) if jain_short else None,
        "aggregate_tok_s": round(sum(e.get("out_tokens") or 0 for e in reqs) /
                                 max(1e-9, max(e["ts"] for e in reqs) -
                                     min(e["ts"] for e in reqs)), 3),
        "short_ttft_bound_s": BOUND_SHORT_TTFT_S,
        "failure_window_s": round(worst, 2) if worst is not None else 0.0,
        "context_policy": {"AG-SHORT": "history-accumulated",
                           "AG-LONG-p32k": "history-accumulated",
                           "AG-LONG-p128kt-hog": "stable-prefix-per-turn (doc stream, "
                                                 "single-turn assembly <=131072)",
                           "AG-BATCH": "single-turn per task"},
        "seed": SEED, "temperature": 0,
    }
    if evict is not None:
        summary["evict"] = evict
    json.dump(summary, open(os.path.join(args.out_dir, "cell-summary.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps({k: summary[k] for k in
                      ("scenario", "policy", "wall_s", "failure_window_s")}, ensure_ascii=False))
    print("per_role:", json.dumps({r: {"ok": v["ok"], "req": v["requests"],
                                       "p95": v["ttft_p95"]} for r, v in roles.items()},
                                  ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["mix", "isolation"], required=False)
    ap.add_argument("--api", required=False)
    ap.add_argument("--policy", required=False, help="blind|role（仅记录于 summary）")
    ap.add_argument("--out-dir", required=False)
    ap.add_argument("--duration-s", type=float, default=150.0, help="isolation 场景墙钟")
    ap.add_argument("--churn-waves", type=int, default=6)
    ap.add_argument("--churn-interval-s", type=float, default=20.0)
    ap.add_argument("--evict-after-s", type=float, default=0, help=">0 启用强驱逐")
    ap.add_argument("--selftest-mock", action="store_true",
                    help="CPU-only 合成自测：SSE mock backends + role router + mini 场景 + schema 断言")
    args = ap.parse_args()
    if args.selftest_mock:
        import ph6_router
        return asyncio.run(_selftest_mock(ph6_router))
    if not (args.scenario and args.api and args.policy and args.out_dir):
        ap.error("--scenario/--api/--policy/--out-dir 必填（或 --selftest-mock）")
    os.makedirs(args.out_dir, exist_ok=True)
    if args.scenario == "mix":
        return asyncio.run(run_mix(args))
    return asyncio.run(run_isolation(args))


async def _sse_mock(port: int, ntok: int, delay_s: float, stop: asyncio.Event):
    """OpenAI SSE mock：delay 后吐 ntok 个 delta + stop + [DONE]。"""
    from aiohttp import web

    async def chat(req):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(req)
        await asyncio.sleep(delay_s)
        for _ in range(ntok):
            chunk = {"id": "mock", "model": "qwen3.8-27b",
                     "choices": [{"index": 0, "delta": {"content": "字 "},
                                  "finish_reason": None}]}
            await resp.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
        fin = {"id": "mock", "model": "qwen3.8-27b",
               "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        await resp.write(f"data: {json.dumps(fin)}\n\n".encode())
        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp

    async def health(req):
        return web.json_response({"ok": True})
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    await stop.wait()
    await runner.cleanup()


async def _selftest_mock(ph6_router) -> int:
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ph6-wl-selftest-")
    # 小型化：prompt 构造替换为微 prompt（仅自测；正式路径用冻结 make_prompt）
    global fixture_prompt
    _orig = fixture_prompt
    fixture_prompt = lambda target, stable_prefix=True: "合成微型 prompt。" * 3  # noqa: E731
    stops = [asyncio.Event() for _ in range(3)]
    ports = [19971, 19972, 19973]
    mocks = [asyncio.create_task(_sse_mock(p, 8, 0.02 if i < 2 else 0.05, s))
             for i, (p, s) in enumerate(zip(ports, stops))]
    await asyncio.sleep(0.4)
    rl = os.path.join(tmp, "routes.jsonl")
    runner = await ph6_router.run_router6(
        [f"p1a=http://127.0.0.1:{ports[0]}", f"p1b=http://127.0.0.1:{ports[1]}",
         f"tp2=http://127.0.0.1:{ports[2]}|131072"],
        19970, rl, role_pools={"short": ["p1a", "p1b"], "long": ["tp2"], "batch": ["p1a", "p1b"]})
    await asyncio.sleep(1.5)

    class _A:
        pass
    ok_all = True
    try:
        # ---- mini mix ----
        a = _A()
        a.scenario, a.policy, a.api = "mix", "role", "http://127.0.0.1:19970/v1"
        a.out_dir = os.path.join(tmp, "mix")
        os.makedirs(a.out_dir, exist_ok=True)
        await run_mix(a)
        s = json.load(open(os.path.join(a.out_dir, "cell-summary.json")))
        assert s["per_role"]["short"]["ok"] >= 2 and s["per_role"]["batch"]["ok"] >= 8 \
            and s["per_role"]["long"]["ok"] >= 3, s["per_role"]
        assert s["fairness_jain_goodput"] is not None and s["failure_window_s"] == 0.0
        # placement：short/batch 全落 p1*，long 全落 tp2
        routes = [json.loads(l) for l in open(rl)]
        for r in routes:
            if r.get("role") == "long":
                assert r["backend"] == "tp2", r
            elif r.get("role") in ("short", "batch"):
                assert r["backend"].startswith("p1"), r
        # ---- mini isolation + evict ----
        b = _A()
        b.scenario, b.policy, b.api = "isolation", "role", "http://127.0.0.1:19970/v1"
        b.out_dir = os.path.join(tmp, "iso")
        os.makedirs(b.out_dir, exist_ok=True)
        b.duration_s, b.churn_waves, b.churn_interval_s, b.evict_after_s = 8.0, 2, 2.0, 3.0
        import types
        await run_isolation(types.SimpleNamespace(**vars(b)))
        s2 = json.load(open(os.path.join(b.out_dir, "cell-summary.json")))
        assert s2["evict"]["evicted_session"] == "hog-1", s2.get("evict")
        assert s2["evict"]["probe_ok"], s2["evict"]
        assert s2["evict"]["release_latency_s"] is not None
        assert all(v == 0 for v in s2["backends_inflight_after"].values()), s2
        # 被逐会话在途请求 → EVICTED 分类存在
        evs = [json.loads(l) for l in open(os.path.join(b.out_dir, "events.jsonl"))]
        assert any(e.get("error_class") == "EVICTED" for e in evs), "被逐会话应有 EVICTED 事件"
    except AssertionError as e:
        ok_all = False
        print(json.dumps({"selftest": "SELFTEST_FAIL", "assert": repr(e)[:300]}))
    finally:
        fixture_prompt = _orig
        await runner.cleanup()
        for s_ in stops:
            s_.set()
        for m in mocks:
            m.cancel()
    if ok_all:
        print(json.dumps({"selftest": "SELFTEST_PASS",
                          "mix": "3 roles ok + placement 100% + jain/failure-window 字段",
                          "isolation": "evict 409→EVICTED 事件 + probe ok + inflight 归零"},
                         ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

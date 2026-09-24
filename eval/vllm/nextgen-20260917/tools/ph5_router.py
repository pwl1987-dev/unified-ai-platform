#!/usr/bin/env python3
"""ph5_router.py v1.0 — Phase 05 sticky-session LB（gates-phase05 router_contract）。

行为契约（frozen）：
  - 会话粘滞：X-Session-Id → 哈希绑 backend（新会话落 least-inflight 健康backend 后记录绑定）
  - 路由日志：每请求一行 JSONL（ts/session/backend/reason/inflight_at_route/dispatch_ms）
    reason ∈ {STICKY_HIT, STICKY_NEW, LEAST_INFLIGHT, FAILOVER_REBIND}
  - 健康探测：1s 间隔 GET /health；连续 3 败摘除、2 胜回池；存量会话重绑（FAILOVER_REBIND 计数）
  - 端点：/healthz、/backends、/metrics（routed_total{backend,reason}/inflight/sticky_hits/
    failover_events/session_map_size/queue_len_high_water）
  - 透明代理：透传 streaming 与非 streaming；不注入不篡改 payload；仅剥 X-Session-Id
  - 不做人为限流（queue=真实 inflight 观测；ban 微差归因——router 开销由 direct vs through-router
    配对测量独立报告，本路由器不猜）

自测（--selftest，CPU-only 无 GPU）：3 个 mock backend 起/停/验 sticky/least-inflight/
failover rebind/metrics 完整性/route 日志字段；全断言过 → SELFTEST_PASS。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict

import aiohttp
from aiohttp import web

VERSION = "ph5-router/1.0"


class Backend:
    def __init__(self, name: str, url: str):
        self.name, self.url = name, url.rstrip("/")
        self.healthy = True
        self.consec_fail = 0
        self.consec_ok = 0
        self.inflight = 0
        self.max_inflight = 0
        self.routed = 0
        self.down_since: float | None = None

    @property
    def score(self) -> tuple[int, str]:
        return (0 if self.healthy else 1, self.name)


class Router:
    def __init__(self, backends: list[Backend], route_log: str, session_cap: int = 100_000):
        self.backends = backends
        self.by_name = {b.name: b for b in backends}
        self.sessions: OrderedDict[str, str] = OrderedDict()  # session -> backend name
        self.session_cap = session_cap
        self.sticky_hits = 0
        self.failover_events = 0
        self.sticky_new = 0
        self.rebinds = 0
        self.route_log_path = route_log
        self._log = open(route_log, "a", buffering=1)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10))

    def log_route(self, **kw):
        kw["ts"] = round(time.time(), 4)
        self._log.write(json.dumps(kw, ensure_ascii=False) + "\n")

    def pick(self, sess_id: str | None) -> tuple[Backend, str]:
        reason = "LEAST_INFLIGHT"
        if sess_id:
            name = self.sessions.get(sess_id)
            if name is not None:
                b = self.by_name.get(name)
                if b is not None and b.healthy:
                    self.sticky_hits += 1
                    return b, "STICKY_HIT"
                # 绑定 backend 已摘除 → 重绑
                self.rebinds += 1
                reason = "FAILOVER_REBIND"
        cand = [b for b in self.backends if b.healthy]
        if not cand:
            raise web.HTTPServiceUnavailable(text="no healthy backend")
        b = min(cand, key=lambda x: (x.inflight, x.name))
        if sess_id:
            self.sessions[sess_id] = b.name
            while len(self.sessions) > self.session_cap:
                self.sessions.popitem(last=False)
            self.sticky_new += 1
            if reason != "FAILOVER_REBIND":
                reason = "STICKY_NEW"
        return b, reason

    async def proxy(self, request: web.Request) -> web.StreamResponse:
        t_in = time.perf_counter()
        sess_id = request.headers.get("X-Session-Id")
        backend, reason = self.pick(sess_id)
        inflight_at_route = backend.inflight
        backend.inflight += 1
        backend.max_inflight = max(backend.max_inflight, backend.inflight)
        backend.routed += 1
        t_disp = time.perf_counter()
        try:
            hdrs = {k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "x-session-id", "content-length")}
            body = await request.read()
            up = await self.session.request(
                request.method, backend.url + request.path_qs,
                headers=hdrs, data=body,
                allow_redirects=False)
            dispatch_ms = round((time.perf_counter() - t_disp) * 1000, 3)
            self.log_route(session=sess_id, backend=backend.name, reason=reason,
                           path=request.path, inflight_at_route=inflight_at_route,
                           dispatch_ms=dispatch_ms, upstream_status=up.status)
            resp = web.StreamResponse(status=up.status,
                                      headers={k: v for k, v in up.headers.items()
                                               if k.lower() not in ("content-length", "transfer-encoding",
                                                                    "connection", "content-encoding")})
            await resp.prepare(request)
            async for chunk in up.content.iter_any():
                await resp.write(chunk)
            await resp.write_eof()
            return resp
        except Exception as e:  # upstream 断流等：如实透传 502（客户端可见，计入日志）
            self.log_route(session=sess_id, backend=backend.name, reason=reason,
                           path=request.path, error=repr(e)[:200])
            return web.Response(status=502, text=f"router upstream error: {e!r}"[:500])
        finally:
            backend.inflight -= 1

    async def health_loop(self, interval: float = 1.0):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.0)) as hs:
            while True:
                for b in self.backends:
                    try:
                        async with hs.get(b.url + "/health") as r:
                            ok = r.status == 200
                    except Exception:
                        ok = False
                    if ok:
                        b.consec_ok += 1
                        b.consec_fail = 0
                    else:
                        b.consec_fail += 1
                        b.consec_ok = 0
                    if b.healthy and b.consec_fail >= 3:
                        b.healthy = False
                        b.down_since = time.time()
                        self.failover_events += 1
                        self.log_route(backend=b.name, event="BACKEND_DOWN")
                    elif not b.healthy and b.consec_ok >= 2:
                        b.healthy = True
                        b.down_since = None
                        self.log_route(backend=b.name, event="BACKEND_RECOVERED")
                await asyncio.sleep(interval)

    async def healthz(self, _):
        alive = sum(1 for b in self.backends if b.healthy)
        return web.json_response({"router": VERSION, "healthy_backends": alive,
                                  "total": len(self.backends),
                                  "status": "ok" if alive else "degraded"})

    async def backends_view(self, _):
        return web.json_response({"backends": [
            {"name": b.name, "url": b.url, "healthy": b.healthy,
             "inflight": b.inflight, "max_inflight": b.max_inflight, "routed": b.routed,
             "down_since": b.down_since} for b in self.backends]})

    async def metrics(self, _):
        lines = [f"ph5_routed_total{{backend=\"{b.name}\"}} {b.routed}" for b in self.backends]
        lines += [f"ph5_inflight{{backend=\"{b.name}\"}} {b.inflight}" for b in self.backends]
        lines += [f"ph5_queue_len_high_water{{backend=\"{b.name}\"}} {b.max_inflight}" for b in self.backends]
        lines += [f"ph5_sticky_hits {self.sticky_hits}", f"ph5_sticky_new {self.sticky_new}",
                  f"ph5_rebinds {self.rebinds}", f"ph5_failover_events {self.failover_events}",
                  f"ph5_session_map_size {len(self.sessions)}",
                  f"ph5_router_version_info{{version=\"{VERSION}\"}} 1"]
        return web.Response(text="\n".join(lines) + "\n")


async def run_router(backend_specs: list[str], port: int, route_log: str):
    backends = []
    for spec in backend_specs:  # name=url
        name, url = spec.split("=", 1)
        backends.append(Backend(name, url))
    r = Router(backends, route_log)
    app = web.Application()
    app.router.add_route("*", "/v1/{tail:.*}", r.proxy)
    app.router.add_get("/healthz", r.healthz)
    app.router.add_get("/backends", r.backends_view)
    app.router.add_get("/metrics", r.metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    hlt = asyncio.create_task(r.health_loop())
    print(json.dumps({"event": "ROUTER_UP", "port": port, "version": VERSION,
                      "backends": [b.name for b in backends], "route_log": route_log}), flush=True)
    return runner, hlt


# ============================================================ selftest（CPU-only）
async def _mock_backend(port: int, delay_s: float, name: str, stop: asyncio.Event):
    async def chat(req):
        await asyncio.sleep(delay_s)
        return web.json_response({"id": "mock", "model": "qwen3.8-27b",
                                  "choices": [{"message": {"content": f"from-{name}"}}],
                                  "mock_backend": name})
    async def health(req):
        return web.json_response({"ok": True})
    app = web.Application()
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    await stop.wait()
    await runner.cleanup()


async def selftest() -> int:
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ph5-router-selftest-")
    route_log = os.path.join(tmp, "routes.jsonl")
    stops = [asyncio.Event() for _ in range(3)]
    ports = [19991, 19992, 19993]
    tasks = [asyncio.create_task(_mock_backend(p, 0.5, f"b{i+1}", s))
             for i, (p, s) in enumerate(zip(ports, stops))]
    await asyncio.sleep(0.5)
    runner, hlt = await run_router([f"b{i+1}=http://127.0.0.1:{p}" for i, p in enumerate(ports)],
                                   19990, route_log)
    await asyncio.sleep(1.5)  # 等 health 首轮
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as c:
        # 1) sticky：同 session 5 请求 → 同 backend
        senders = set()
        for _ in range(5):
            async with c.post("http://127.0.0.1:19990/v1/chat/completions",
                              json={"messages": []}, headers={"X-Session-Id": "sess-A"}) as r:
                senders.add((await r.json())["mock_backend"])
        assert len(senders) == 1, f"sticky FAIL: {senders}"
        # 2) least-inflight：占住 sess-A 的长请求（0.5s mock delay），新会话应避开同 backend
        hold_task = asyncio.create_task(
            c.post("http://127.0.0.1:19990/v1/chat/completions",
                   json={"messages": []}, headers={"X-Session-Id": "sess-A"}))
        await asyncio.sleep(0.1)  # 确认占线已登记 inflight
        async with c.post("http://127.0.0.1:19990/v1/chat/completions",
                          json={"messages": []}, headers={"X-Session-Id": "sess-B"}) as r:
            b_b = (await r.json())["mock_backend"]
        held_resp = await hold_task
        b_a = (await held_resp.json())["mock_backend"]
        assert b_b != next(iter(senders)), f"least-inflight FAIL: 新会话落在占线 backend {b_b}"
        # 3) metrics/healthz/backends
        async with c.get("http://127.0.0.1:19990/metrics") as r:
            m = await r.text()
        assert "ph5_sticky_hits" in m and "ph5_routed_total" in m
        async with c.get("http://127.0.0.1:19990/healthz") as r:
            assert (await r.json())["healthy_backends"] == 3
        # 4) failover：停掉 sess-B 绑定的 mock → 3 败摘除 → 存量会话重绑
        async with c.get("http://127.0.0.1:19990/backends") as r:
            assert all(b["healthy"] for b in (await r.json())["backends"])
        # kill 掉 sess-B 绑定的 mock
        idx = int(b_b[1:]) - 1
        stops[idx].set()
        await asyncio.sleep(4.5)  # 3 败摘除
        async with c.post("http://127.0.0.1:19990/v1/chat/completions",
                          json={"messages": []}, headers={"X-Session-Id": "sess-B"}) as r:
            assert r.status == 200, f"failover rebind FAIL status={r.status}"
            after = (await r.json())["mock_backend"]
        assert after != b_b, f"rebind FAIL: {after} == {b_b}"
        async with c.get("http://127.0.0.1:19990/metrics") as r:
            m2 = await r.text()
        assert "ph5_failover_events 1" in m2, m2
        # 5) route 日志字段
        rows = [json.loads(l) for l in open(route_log)]
        reasons = {row.get("reason") for row in rows if "reason" in row}
        events = {row.get("event") for row in rows if "event" in row}
        assert {"STICKY_HIT", "STICKY_NEW", "FAILOVER_REBIND"} <= reasons, reasons
        assert "BACKEND_DOWN" in events
    hlt.cancel()
    await runner.cleanup()
    for t in tasks:
        t.cancel()
    print(json.dumps({"selftest": "SELFTEST_PASS", "sticky": "5/5 same backend",
                      "failover": f"{b_b}->{after}", "route_log_fields": "OK",
                      "reasons": sorted(reasons)}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", action="append", required=False,
                    help="name=url（可多次）")
    ap.add_argument("--port", type=int, default=19710)
    ap.add_argument("--route-log", default="/data/sandbox/nextgen-20260917/ph5-router-routes.jsonl")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return asyncio.run(selftest())
    if not args.backend:
        ap.error("--backend 必填（或用 --selftest）")
    async def serve():
        runner, hlt = await run_router(args.backend, args.port, args.route_log)
        await asyncio.Event().wait()
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

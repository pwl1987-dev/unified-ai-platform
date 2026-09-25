#!/usr/bin/env python3
"""ph6_router.py v2.0 — Phase 06 角色化路由 + 强驱逐 router（gates-phase06 routing_ab）。

设计（单变量纪律）：
  - 直接继承 ph5_router.Router（v1.1 冻结语义）：未配置 --role-pools 时行为与 v1.1 逐位一致
    （selftest 断言：同流量序列下与 ph5_router.Router 决策序列完全相同）。
  - --role-pools "short=b1,b2;long=b3;batch=b1,b2" 启用 B_ROLE 策略：
      role → 池内（healthy ∧ fits）least-inflight；sticky 绑定仅在池内有效；
      绑定在池外 → ROLE_REROUTE 重绑；池内无可容纳 → ROLE_FALLBACK 全局回退（长度守卫仍强制）；
      无 X-Role / 未知 role → 回退 v1.1 语义。
  - /admin/evict?session=X：强驱逐——中止该会话在途请求（客户端收 409 SESSION_EVICTED，
    不得挂起）、解绑 session map；驱逐后宽限窗内该会话新请求一律 409 EVICTED；
    其余会话零影响（selftest 断言）。
  - route log 增 role/evict 字段；/metrics 增 ph6_role_routed_total/ph6_evictions 等。

自测（--selftest，CPU-only）：v1.1 parity（决策序列逐位对照）+ 六断言移植 + role 路由
+ role×长度守卫 + 驱逐（在途中止/后续 409/他者无扰/inflight 归零）。全过 → SELFTEST_PASS。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

import aiohttp
from aiohttp import web

import ph5_router
from ph5_router import Router, run_router  # noqa: F401  (run_router 复用：blind 模式直接可用)

VERSION = "ph6-router/2.0"
EVICT_GRACE_S = 60.0


class Ph6Router(Router):
    def __init__(self, *a, role_pools: dict[str, list[str]] | None = None, **kw):
        super().__init__(*a, **kw)
        self.role_pools = role_pools          # None = blind parity（v1.1）
        self.role_routed: dict[str, int] = {}
        self.role_fallbacks = 0
        self.evictions = 0
        self.evicted_rejects = 0
        self.evicted: dict[str, float] = {}   # sid -> evict ts
        self.upstreams: dict[str, set] = {}   # sid -> {ClientResponse}

    # ---------------- role-aware pick ----------------
    def pick(self, sess_id: str | None, need: int | None = None, role: str | None = None):
        if not self.role_pools or role is None or role not in self.role_pools:
            return super().pick(sess_id, need)          # 逐字 v1.1 语义
        self.role_routed[role] = self.role_routed.get(role, 0) + 1
        pool = [self.by_name[n] for n in self.role_pools[role] if n in self.by_name]
        cand = [b for b in pool if b.healthy and b.fits(need)]
        if not cand:
            self.role_fallbacks += 1
            b, reason = super().pick(sess_id, need)      # 长度守卫/failover 语义复用
            return b, f"ROLE_FALLBACK_{reason}"
        # sticky 仅在池内有效
        if sess_id:
            name = self.sessions.get(sess_id)
            if name is not None:
                b = self.by_name.get(name)
                if b is not None and b in cand:
                    self.sticky_hits += 1
                    return b, "ROLE_STICKY_HIT"
                if b is not None and b.healthy and b.fits(need):
                    self.rebinds += 1     # 绑定 backend 不在本 role 池 → 重绑（角色变更/池划分变化）
        b = min(cand, key=lambda x: (x.inflight, x.name))
        if sess_id:
            self.sessions[sess_id] = b.name
            while len(self.sessions) > self.session_cap:
                self.sessions.popitem(last=False)
            self.sticky_new += 1
        return b, "ROLE_NEW"

    # ---------------- eviction ----------------
    def evict(self, sess_id: str) -> dict:
        self.evictions += 1
        self.evicted[sess_id] = time.time()
        self.sessions.pop(sess_id, None)
        resp_closed = 0
        for resp in list(self.upstreams.get(sess_id, ())):
            try:
                resp.close()                     # 中止在途上游流
                resp_closed += 1
            except Exception:
                pass
        self.log_route(session=sess_id, event="SESSION_EVICTED", closed_upstreams=resp_closed)
        return {"evicted": sess_id, "closed_upstreams": resp_closed,
                "evicted_active_sessions": len(self.evicted)}

    def _is_evicted(self, sess_id: str | None) -> bool:
        if not sess_id or sess_id not in self.evicted:
            return False
        if time.time() - self.evicted[sess_id] > EVICT_GRACE_S:
            del self.evicted[sess_id]            # 宽限窗过 → 该 sid 可重新进入
            return False
        return True

    # ---------------- proxy（注册 upstream 以支持驱逐中止）----------------
    async def proxy(self, request: web.Request) -> web.StreamResponse:
        sess_id = request.headers.get("X-Session-Id")
        if self._is_evicted(sess_id):
            self.evicted_rejects += 1
            self.log_route(session=sess_id, reason="EVICTED_REJECT", upstream_status=409)
            return web.json_response(
                {"error": {"code": "SESSION_EVICTED", "message": "session force-evicted"}},
                status=409)
        role = request.headers.get("X-Role")
        need = None
        if request.method == "POST" and request.path.endswith("/chat/completions"):
            try:
                body = await request.json()
                need = ph5_router.est_tokens(body)
            except Exception:
                body = None
        else:
            body = None
        backend, reason = self.pick(sess_id, need, role)
        inflight_at_route = backend.inflight
        backend.inflight += 1
        backend.max_inflight = max(backend.max_inflight, backend.inflight)
        backend.routed += 1
        t_disp = time.perf_counter()
        up = None
        try:
            hdrs = {k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "x-session-id", "x-role", "content-length")}
            data = json.dumps(body).encode() if body is not None else await request.read()
            up = await self.session.request(
                request.method, backend.url + request.path_qs,
                headers=hdrs, data=data, allow_redirects=False)
            dispatch_ms = round((time.perf_counter() - t_disp) * 1000, 3)
            self.log_route(session=sess_id, backend=backend.name, reason=reason, role=role,
                           path=request.path, inflight_at_route=inflight_at_route,
                           est_tokens=need, dispatch_ms=dispatch_ms, upstream_status=up.status)
            if sess_id:
                self.upstreams.setdefault(sess_id, set()).add(up)
            if self._is_evicted(sess_id):              # pre-head 驱逐：干净 409
                up.close()
                self.evicted_rejects += 1
                return web.json_response(
                    {"error": {"code": "SESSION_EVICTED",
                               "message": "session force-evicted pre-head"}}, status=409)
            resp = web.StreamResponse(
                status=up.status,
                headers={k: v for k, v in up.headers.items()
                         if k.lower() not in ("content-length", "transfer-encoding",
                                              "connection", "content-encoding")})
            await resp.prepare(request)
            async for chunk in up.content.iter_any():
                if self._is_evicted(sess_id):
                    raise ConnectionError("session evicted mid-stream")
                await resp.write(chunk)
            await resp.write_eof()
            return resp
        except Exception as e:
            evicted = self._is_evicted(sess_id)
            self.log_route(session=sess_id, backend=backend.name, reason=reason, role=role,
                           path=request.path, error=repr(e)[:200],
                           evicted=evicted, upstream_status=409 if evicted else 502)
            if evicted:
                self.evicted_rejects += 1
                return web.json_response(
                    {"error": {"code": "SESSION_EVICTED",
                               "message": "session force-evicted mid-stream"}}, status=409)
            return web.Response(status=502, text=f"router upstream error: {e!r}"[:500])
        finally:
            if sess_id and up is not None:
                self.upstreams.get(sess_id, set()).discard(up)
                if not self.upstreams.get(sess_id):
                    self.upstreams.pop(sess_id, None)
            backend.inflight -= 1

    async def admin_evict(self, request: web.Request):
        sid = request.query.get("session")
        if not sid:
            return web.json_response({"error": "session param required"}, status=400)
        return web.json_response(self.evict(sid))

    async def metrics(self, _):
        lines = await super().metrics(_)
        extra = [f"ph6_role_routed_total{{role=\"{r}\"}} {n}" for r, n in self.role_routed.items()]
        extra += [f"ph6_role_fallbacks {self.role_fallbacks}",
                  f"ph6_evictions {self.evictions}",
                  f"ph6_evicted_rejects {self.evicted_rejects}",
                  f"ph6_router_version_info{{version=\"{VERSION}\"}} 1"]
        return web.Response(text=lines.text + "\n".join(extra) + "\n")


async def run_router6(backend_specs: list[str], port: int, route_log: str,
                      role_pools: dict[str, list[str]] | None = None):
    backends = []
    for spec in backend_specs:  # name=url|max_len（v1.1 同解析）
        name, rest = spec.split("=", 1)
        url, sep, ml = rest.rpartition("|")
        if not sep or not ml.isdigit():
            url, ml = rest, ""
        backends.append(ph5_router.Backend(name, url, int(ml) if ml else None))
    r = Ph6Router(backends, route_log, role_pools=role_pools)
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_route("*", "/v1/{tail:.*}", r.proxy)
    app.router.add_get("/healthz", r.healthz)
    app.router.add_get("/backends", r.backends_view)
    app.router.add_get("/metrics", r.metrics)
    app.router.add_post("/admin/evict", r.admin_evict)
    app.router.add_get("/admin/evict", r.admin_evict)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    asyncio.create_task(r.health_loop())
    print(json.dumps({"event": "ROUTER_UP", "port": port, "version": VERSION,
                      "mode": "ROLE" if role_pools else "BLIND_PARITY",
                      "role_pools": role_pools, "route_log": route_log}), flush=True)
    return runner


# ============================================================ selftest（CPU-only）
async def _mock_backend(port: int, delay_s: float, name: str, stop: asyncio.Event):
    """非流式 mock：delay_s 模拟 prefill+decode 全程（evict 自测用 3s 保证落在 pre-head 窗）。"""
    async def chat(req):
        await asyncio.sleep(delay_s)
        return web.json_response({"id": "mock", "model": "qwen3.8-27b",
                                  "choices": [{"message": {"content": f"from-{name}"}}],
                                  "mock_backend": name})

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


async def selftest() -> int:
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ph6-router-selftest-")
    rl = os.path.join(tmp, "routes.jsonl")
    stops = [asyncio.Event() for _ in range(3)]
    ports = [19981, 19982, 19983]
    tasks = [asyncio.create_task(_mock_backend(p, 0.05, f"b{i+1}", s))
             for i, (p, s) in enumerate(zip(ports, stops))]
    await asyncio.sleep(0.4)
    runner = await run_router6([f"b{i+1}=http://127.0.0.1:{p}" for i, p in enumerate(ports)],
                               19980, rl)                      # BLIND parity 模式
    await asyncio.sleep(1.5)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as c:
        # --- 0) v1.1 parity：同流量序列决策逐位一致 ---
        ref = ph5_router.Router(
            [ph5_router.Backend(f"b{i+1}", f"http://127.0.0.1:{p}") for i, p in enumerate(ports)],
            os.path.join(tmp, "ref-routes.jsonl"))
        seq = [("sA", None), ("sA", None), ("sB", None), ("sA", None), ("sC", None), ("sB", None)]
        ref_picks = [ref.pick(s, None)[0].name for s, _ in seq]
        r6 = None
        # 取 Ph6Router 实例做同样序列（直接走内部对象保证同初态）
        # runner 内 router 引用经 /backends 无法拿到；改用 HTTP 验证 sticky+least-inflight 等价断言
        # （v1.1 决策 = sticky → least-inflight(name 序）；下断言 1/2 即 parity 的可观察面）
        # --- 1) sticky 5/5 同 backend ---
        senders = set()
        for _ in range(5):
            async with c.post("http://127.0.0.1:19980/v1/chat/completions",
                              json={"messages": []}, headers={"X-Session-Id": "sess-A"}) as r:
                senders.add((await r.json())["mock_backend"])
        assert len(senders) == 1, f"sticky FAIL {senders}"
        # --- parity 内部对照（直接实例级）---
        ph6r = Ph6Router(
            [ph5_router.Backend(f"b{i+1}", f"http://127.0.0.1:{p}") for i, p in enumerate(ports)],
            os.path.join(tmp, "ph6-obj-routes.jsonl"))
        ph6_picks = [ph6r.pick(s, None)[0].name for s, _ in seq]
        assert ph6_picks == ref_picks, f"PARITY FAIL {ph6_picks} != {ref_picks}"
        # --- 2) least-inflight：长请求占线时新会话避开 ---
        hold = asyncio.create_task(
            c.post("http://127.0.0.1:19980/v1/chat/completions",
                   json={"messages": []}, headers={"X-Session-Id": "sess-A2"}))
        await asyncio.sleep(0.02)
        async with c.post("http://127.0.0.1:19980/v1/chat/completions",
                          json={"messages": []}, headers={"X-Session-Id": "sess-B"}) as r:
            b_b = (await r.json())["mock_backend"]
        await hold
        assert b_b != "b1", f"least-inflight FAIL {b_b}"
        # --- 3) metrics 字段（v1.1 + ph6 增量）---
        async with c.get("http://127.0.0.1:19980/metrics") as r:
            m = await r.text()
        assert "ph5_sticky_hits" in m and "ph6_evictions" in m and "ph6_router_version_info" in m
        # --- 4) failover：停 sess-B 绑定 mock → 重绑 ---
        idx = int(b_b[1:]) - 1
        stops[idx].set()
        await asyncio.sleep(4.5)
        async with c.post("http://127.0.0.1:19980/v1/chat/completions",
                          json={"messages": []}, headers={"X-Session-Id": "sess-B"}) as r:
            assert r.status == 200
            after = (await r.json())["mock_backend"]
        assert after != b_b
        # --- 5) route 日志字段 ---
        rows = [json.loads(l) for l in open(rl)]
        assert any(r.get("reason") == "STICKY_HIT" for r in rows)
        assert any(r.get("event") == "BACKEND_DOWN" for r in rows)
    # --- 6) 长度守卫 + role（独立实例，带 max_len 与 role 池）---
    rl2 = os.path.join(tmp, "routes-role.jsonl")
    stop2 = asyncio.Event()
    ports2 = [19984, 19985]
    t2s = [asyncio.create_task(_mock_backend(p, 0.05, f"g{i+1}", stop2))
           for i, p in enumerate(ports2)]
    await asyncio.sleep(0.4)
    runner2 = await run_router6(
        [f"g1=http://127.0.0.1:{ports2[0]}|4096", f"g2=http://127.0.0.1:{ports2[1]}|131072"],
        19986, rl2, role_pools={"short": ["g1"], "long": ["g2"], "batch": ["g1"]})
    await asyncio.sleep(1.5)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as c:
        H = {"Content-Type": "application/json"}
        async with c.post("http://127.0.0.1:19986/v1/chat/completions",
                          json={"messages": [{"role": "user", "content": "短"}], "max_tokens": 32},
                          headers={**H, "X-Session-Id": "r-s", "X-Role": "short"}) as r:
            assert (await r.json())["mock_backend"] == "g1", "role short 应落 g1"
        async with c.post("http://127.0.0.1:19986/v1/chat/completions",
                          json={"messages": [{"role": "user", "content": "短"}], "max_tokens": 32},
                          headers={**H, "X-Session-Id": "r-l", "X-Role": "long"}) as r:
            assert (await r.json())["mock_backend"] == "g2", "role long 应落 g2"
        # role sticky：同 short 会话再发 → 仍 g1（ROLE_STICKY_HIT）
        async with c.post("http://127.0.0.1:19986/v1/chat/completions",
                          json={"messages": [{"role": "user", "content": "短"}], "max_tokens": 32},
                          headers={**H, "X-Session-Id": "r-s", "X-Role": "short"}) as r:
            assert (await r.json())["mock_backend"] == "g1"
        # role×长度守卫：long role 但 prompt 超 g2 max_len → 400（守卫不因 role 放弃）
        async with c.post("http://127.0.0.1:19986/v1/chat/completions",
                          json={"messages": [{"role": "user", "content": "长" * 200000}],
                                "max_tokens": 32},
                          headers={**H, "X-Session-Id": "r-huge", "X-Role": "long"}) as r:
            assert r.status == 400, f"role len-guard FAIL {r.status}"
        # 无 role 头 → 回退 v1.1（least-inflight name 序 → g1）
        async with c.post("http://127.0.0.1:19986/v1/chat/completions",
                          json={"messages": [{"role": "user", "content": "短"}], "max_tokens": 32},
                          headers={**H, "X-Session-Id": "r-none"}) as r:
            assert (await r.json())["mock_backend"] == "g1"
    # --- 7) 驱逐（3s mock：evict 时在途请求落在 pre-head 窗 → 干净 409；他人无扰；宽限 409）---
    rl3 = os.path.join(tmp, "routes-evict.jsonl")
    stop3 = asyncio.Event()
    t3 = asyncio.create_task(_mock_backend(19987, 3.0, "e1", stop3))
    await asyncio.sleep(0.4)
    runner3 = await run_router6(["e1=http://127.0.0.1:19987"], 19988, rl3)
    await asyncio.sleep(1.5)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as c:
        async def one(sid):
            async with c.post("http://127.0.0.1:19988/v1/chat/completions",
                              json={"messages": [{"role": "user", "content": "x"}], "max_tokens": 32},
                              headers={"X-Session-Id": sid}) as r:
                return r.status, await r.read()
        victim = asyncio.create_task(one("hog"))
        bystander = asyncio.create_task(one("nice"))
        await asyncio.sleep(0.5)          # 两请求均已在途（pre-head）
        async with c.post("http://127.0.0.1:19988/admin/evict?session=hog") as r:
            ev = await r.json()
        assert ev["evicted"] == "hog", ev
        vs, vb = await victim
        bs, bb = await bystander
        assert vs == 409 and b"SESSION_EVICTED" in vb, f"evict 在途应 409，得 {vs} {vb[:60]}"
        assert bs == 200, f"bystander 不应受驱逐影响，得 {bs}"
        # 宽限窗内该会话新请求 409
        async with c.post("http://127.0.0.1:19988/v1/chat/completions",
                          json={"messages": []}, headers={"X-Session-Id": "hog"}) as r:
            assert r.status == 409
        # inflight 归零
        async with c.get("http://127.0.0.1:19988/metrics") as r:
            m3 = await r.text()
        assert "ph5_inflight{backend=\"e1\"} 0" in m3, m3
    for rt in (runner, runner2, runner3):
        await rt.cleanup()
    for t in (*tasks, *t2s, t3):
        t.cancel()
    stop3.set()
    print(json.dumps({"selftest": "SELFTEST_PASS",
                      "parity": f"{ph6_picks} == {ref_picks}",
                      "role": "short->g1 long->g2 sticky-ok len-guard-400 no-role->fallback",
                      "evict": "in-flight 409 / bystander 200 / grace 409 / inflight 0"},
                     ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", action="append")
    ap.add_argument("--port", type=int, default=19710)
    ap.add_argument("--route-log", default="/data/sandbox/nextgen-20260917/ph6-router-routes.jsonl")
    ap.add_argument("--role-pools", default="",
                    help='short=b1,b2;long=b3;batch=b1,b2（空=blind parity v1.1）')
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return asyncio.run(selftest())
    if not args.backend:
        ap.error("--backend 必填（或 --selftest）")
    pools = None
    if args.role_pools:
        pools = {}
        for grp in args.role_pools.split(";"):
            role, _, names = grp.partition("=")
            pools[role.strip()] = [n.strip() for n in names.split(",") if n.strip()]

    async def serve():
        await run_router6(args.backend, args.port, args.route_log, pools)
        await asyncio.Event().wait()
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

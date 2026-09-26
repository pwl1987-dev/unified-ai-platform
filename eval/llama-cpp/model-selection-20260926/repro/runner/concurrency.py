"""concurrency.py — C1/C2/C4/C8 against a -np N llama-server (shared ctx pool).
Records aggregate/per-request TPS, TTFT p50/p95/p99, failures, VRAM.
Usage: uv run python concurrency.py <image> <gpu> <model_path> <model_key> <ctx> [port]
"""
from __future__ import annotations
import asyncio, json, statistics, sys, time

sys.path.insert(0, "/data/tasks/qwen-model-lab/ops/llama-cpp-model-lab/runner")
import lab
import httpx


async def one(client, port, payload_t0, i):
    t0 = time.time()
    ttft = None
    toks = 0
    async with client.stream("POST", f"http://127.0.0.1:{port}/v1/chat/completions", json={
            "messages": [{"role": "user", "content": f"第{i}号请求：用两句话解释 epoll。"}],
            "max_tokens": 220, "temperature": 0.0, "seed": 42 + i, "stream": True,
            "stream_options": {"include_usage": True}}) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if not line.startswith("data: "):
                continue
            d = line[6:]
            if d.strip() == "[DONE]":
                break
            try:
                j = json.loads(d)
            except Exception:
                continue
            if ttft is None and (j.get("choices") and j["choices"][0].get("delta", {}).get("content")):
                ttft = time.time() - t0
            if j.get("usage"):
                toks = j["usage"].get("completion_tokens", 0)
    return {"i": i, "ttft": ttft, "wall": time.time() - t0, "toks": toks}


async def wave(port, n):
    limits = httpx.Limits(max_connections=n + 4)
    async with httpx.AsyncClient(timeout=600, limits=limits) as client:
        t0 = time.time()
        res = await asyncio.gather(*[one(client, port, None, i) for i in range(n)], return_exceptions=True)
        wall = time.time() - t0
    ok = [r for r in res if isinstance(r, dict)]
    errs = [str(r)[:100] for r in res if not isinstance(r, dict)]
    tt = sorted(x["ttft"] or 1e9 for x in ok)
    agg = sum(x["toks"] for x in ok) / wall if wall else 0
    def pct(p):
        return round(tt[min(int(len(tt) * p), len(tt) - 1)], 2) if tt else None
    return {"n": n, "ok": len(ok), "errors": errs[:3], "wall_s": round(wall, 2),
            "aggregate_tps": round(agg, 1),
            "per_req_tps": round(statistics.mean([x["toks"] / x["wall"] for x in ok if x["wall"] > 0]), 2) if ok else 0,
            "ttft_p50": pct(0.5), "ttft_p95": pct(0.95), "ttft_p99": pct(0.99)}


async def amain():
    image, gpu, model_path, key, ctx = sys.argv[1:6]
    ctx = int(ctx)
    port = int(sys.argv[6]) if len(sys.argv) > 6 else 18211
    np_slots = int(sys.argv[7]) if len(sys.argv) > 7 else 8
    cname = f"conc-{key}"
    cmd = (f"-m {model_path} --host 0.0.0.0 --port 8080 -c {ctx} -np {np_slots} -ngl 999 "
           f"--cache-type-k q4_0 --cache-type-v q4_0 -fa on --jinja -a conc "
           f"-b 2048 -ub 512 --metrics")
    rec = {"model": key, "ctx_total": ctx, "np": np_slots, "waves": []}
    lab.server_up(cname, image, port, gpu, cmd)
    rec["vram_after_load"] = lab.vram_mib(gpu)
    # warmup
    await wave(port, 1)
    for n in (1, 2, 4, 8):
        r = await wave(port, n)
        r["vram"] = lab.vram_mib(gpu)
        rec["waves"].append(r)
        print(f"  C{n}: {json.dumps(r, ensure_ascii=False)}", flush=True)
        await asyncio.sleep(2)
    lab.write_json(lab.EVID / "runs" / "concurrency" / f"{key}.json", rec)
    lab.server_down(cname)
    print("CONC DONE")


if __name__ == "__main__":
    asyncio.run(amain())

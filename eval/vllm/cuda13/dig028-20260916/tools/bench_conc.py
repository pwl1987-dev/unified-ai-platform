#!/usr/bin/env python3
"""并发 fixture：C 路并发流式请求，测 per-request TTFT/decode 与聚合吞吐。
用法: bench_conc.py <api> <profile> <out.json> <concurrency> [max_tokens=256] [prompt_target=512]"""
import json
import sys
import threading
import time
import urllib.request

sys.path.insert(0, "/data/repos/qwen3.8-27b-8x4090-stack/inference/vllm/bench")
from ulmus_validate import make_prompt  # noqa: E402

API, PROFILE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
C = int(sys.argv[4])
MAXTOK = int(sys.argv[5]) if len(sys.argv) > 5 else 256
PTARGET = int(sys.argv[6]) if len(sys.argv) > 6 else 512
PROMPT = make_prompt(PTARGET)


def one(i, results):
    payload = {
        "model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAXTOK, "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": f"conc-{PROFILE}-{i}",
    }
    req = urllib.request.Request(API + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first, ntok, usage = None, 0, None
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data: "):
                    continue
                if line[6:] == "[DONE]":
                    break
                obj = json.loads(line[6:])
                d = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                if d:
                    ntok += 1
                    if first is None:
                        first = time.monotonic() - t0
                if obj.get("usage"):
                    usage = obj["usage"]
        wall = time.monotonic() - t0
        ct = (usage or {}).get("completion_tokens", ntok)
        results[i] = {"ttft_s": round(first, 3) if first else None,
                      "wall_s": round(wall, 2), "completion_tokens": ct,
                      "decode_tok_s": round(ct / wall, 1)}
    except Exception as e:  # noqa: BLE001
        results[i] = {"error": str(e)[:120]}


barrier = threading.Barrier(C)


def runner(i):
    barrier.wait()
    one(i, results)


results = {}
threads = [threading.Thread(target=runner, args=(i,)) for i in range(C)]
t_start = time.monotonic()
for t in threads:
    t.start()
for t in threads:
    t.join()
span = time.monotonic() - t_start
total_tok = sum(r.get("completion_tokens", 0) for r in results.values())
ok = [r for r in results.values() if "error" not in r]
report = {
    "profile": PROFILE, "concurrency": C, "max_tokens": MAXTOK,
    "span_s": round(span, 2),
    "aggregate_tok_s": round(total_tok / span, 1),
    "per_stream_decode_tok_s": [r.get("decode_tok_s") for r in ok],
    "ttft_s": [r.get("ttft_s") for r in ok],
    "errors": [r["error"] for r in results.values() if "error" in r],
    "detail": results,
}
with open(OUT, "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
print(json.dumps({k: report[k] for k in
                  ("profile", "concurrency", "span_s", "aggregate_tok_s",
                   "per_stream_decode_tok_s", "ttft_s", "errors")},
                 ensure_ascii=False))

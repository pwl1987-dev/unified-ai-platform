#!/usr/bin/env python3
"""partial-tail 前缀复用 TTFT 探针（#50507 验证）。
三次测 TTFT：冷全量 / 同文重发（应全命中）/ 尾部改写（partial-tail 应只重算尾段）。
用法: probe_prefix.py <api> <profile> <out.json>"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/data/repos/qwen3.8-27b-8x4090-stack/inference/vllm/bench")
from ulmus_validate import make_prompt  # noqa: E402

API, PROFILE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BASE = make_prompt(4096)
TAIL = "\n\n补充说明：本条为尾部改写变体，用于测试部分前缀复用行为，编号 ALPHA-77。"
PROMPTS = {
    "cold_full": BASE + "\n（原始版本）",
    "warm_same": BASE + "\n（原始版本）",
    "tail_modified": BASE + TAIL,
}


def ttft(content):
    payload = {
        "model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4, "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(API + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first = None
    cached = None
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            if line[6:] == "[DONE]":
                break
            obj = json.loads(line[6:])
            if first is None and (obj.get("choices") or [{}])[0].get("delta", {}).get("content"):
                first = time.monotonic() - t0
            if "usage" in obj and obj["usage"]:
                cached = obj["usage"].get("prompt_tokens_details", {}).get("cached_tokens")
    return {"ttft_s": round(first, 3), "cached_tokens": cached}


results = {}
for name, content in PROMPTS.items():
    results[name] = ttft(content)
    time.sleep(1)
report = {"profile": PROFILE, "results": results}
with open(OUT, "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
print(json.dumps(report, ensure_ascii=False))

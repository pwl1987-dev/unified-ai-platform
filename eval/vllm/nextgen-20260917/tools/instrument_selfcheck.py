#!/usr/bin/env python3
"""仪器自校验（Harness Gate v2.1 第 3 条，MASTER §4.3）。

对一个已知短请求各跑 streaming / non-streaming 一次：
- token 计数（client chunk 数）与 server usage 交叉核对；
- TTFB 与 TTFT 分记；
- 服务端返回的 prompt_tokens 与 tokenizer 离线计数对照（如可用）。

用法: instrument_selfcheck.py --api http://127.0.0.1:PORT/v1 --out selfcheck.json
退出码 0=全过。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sseparser import SSEParser, extract_content  # noqa: E402

KNOWN_PROMPT = "请从 1 数到 20，每个数字一行，只输出数字。"
EXPECTED_MAX_TOKENS = 128


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--out", default="selfcheck.json")
    args = ap.parse_args()
    base = {"model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": KNOWN_PROMPT}],
            "max_tokens": EXPECTED_MAX_TOKENS,
            "cache_salt": "warmup-selfcheck"}

    # streaming
    payload = {**base, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(args.api + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic_ns()
    parser = SSEParser()
    first_header = first_token = None
    stream_text_parts: list[str] = []
    with urllib.request.urlopen(req, timeout=120) as r:
        t_hdr = (time.monotonic_ns() - t0) / 1e9
        while True:
            line = r.readline()
            if not line:
                break
            for ev in parser.feed(line):
                if ev["kind"] != "data" or ev.get("malformed"):
                    continue
                c = extract_content(ev["json"])
                if c:
                    stream_text_parts.append(c)
                    if first_token is None:
                        first_token = (time.monotonic_ns() - t0) / 1e9
    parser.flush()
    usage = None
    for ev in parser.events:
        if ev["kind"] == "data" and isinstance(ev.get("json"), dict) and ev["json"].get("usage"):
            usage = ev["json"]["usage"]
    stream_text = "".join(stream_text_parts)
    # 注意：spec decode 下一个 SSE chunk 可含多个 token，
    # chunk 数 ≠ token 数；token 等价性由"流式/非流式拼接文本一致"保证
    client_event_count = len(stream_text_parts)

    # non-streaming
    payload2 = {**base, "stream": False}
    req2 = urllib.request.Request(args.api + "/chat/completions",
                                  data=json.dumps(payload2).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req2, timeout=120) as r2:
        obj = json.load(r2)
    ns_usage = obj.get("usage") or {}
    ns_text = (obj.get("choices") or [{}])[0].get("message", {}).get("content") or ""

    report = {
        "stream": {
            "ttfb_s": round(t_hdr, 4),
            "ttft_s": round(first_token, 4) if first_token else None,
            "client_event_count": client_event_count,
            "server_completion_tokens": (usage or {}).get("completion_tokens"),
            "server_prompt_tokens": (usage or {}).get("prompt_tokens"),
        },
        "non_stream": {
            "server_completion_tokens": ns_usage.get("completion_tokens"),
            "server_prompt_tokens": ns_usage.get("prompt_tokens"),
            "content_char_len": len(ns_text),
        },
        "stream_text_sha256": __import__("hashlib").sha256(
            stream_text.encode()).hexdigest(),
        "nonstream_text_sha256": __import__("hashlib").sha256(
            ns_text.encode()).hexdigest(),
    }
    report["checks"] = {
        "stream_vs_nonstream_text_match": stream_text == ns_text,
        "prompt_tokens_consistent_modes":
            (usage or {}).get("prompt_tokens") == ns_usage.get("prompt_tokens"),
        "completion_tokens_consistent_modes":
            (usage or {}).get("completion_tokens") == ns_usage.get("completion_tokens"),
        "ttfb_le_ttft": first_token is None or t_hdr <= first_token,
        "usage_present_stream": usage is not None,
        "nonempty_stream_text": len(stream_text) > 0,
    }
    all_ok = all(report["checks"].values())
    report["PASS"] = all_ok
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps(report, ensure_ascii=False))
    print("SELFCHECK_" + ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

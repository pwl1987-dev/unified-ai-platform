#!/usr/bin/env python3
"""nextgen needle 探针 — 判定规则与 dig028 needle_probe.py 一致，seed 参数化。

- 位置百分位固定 10/30/50/70/90（gen_fixtures.make_needle_fixture）
- 每请求唯一 cache_salt（独立冷上下文，禁把 prefix hit 当冷能力）
- 记录 ttft/wall/answer/逐码命中；PASS = 5/5 exact
用法: needle_probe_nextgen.py --api URL --prompt-tokens 238000 --seed 1 \
        --experiment-id ID --out-dir DIR [--salt-namespace formal]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_fixtures import make_needle_fixture  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--prompt-tokens", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--salt-namespace", default="formal")
    args = ap.parse_args()

    doc, needles = make_needle_fixture(args.prompt_tokens, args.seed)
    fixture_sha = hashlib.sha256(doc.encode()).hexdigest()
    salt = f"{args.salt_namespace}-needle-{args.experiment_id}"
    payload = {
        "model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": doc}],
        "max_tokens": args.max_tokens, "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": salt,
    }
    req = urllib.request.Request(args.api + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic_ns()
    first, chunks, usage = None, [], None
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            if line[6:] == "[DONE]":
                break
            obj = json.loads(line[6:])
            d = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
            if d:
                chunks.append(d)
                if first is None:
                    first = (time.monotonic_ns() - t0) / 1e9
            if obj.get("usage"):
                usage = obj["usage"]
    wall = (time.monotonic_ns() - t0) / 1e9
    text = "".join(chunks)
    per_needle = {c: (c in text) for c in needles}
    hits = sum(per_needle.values())
    report = {
        "experiment_id": args.experiment_id,
        "prompt_tokens_target": args.prompt_tokens,
        "actual_prompt_tokens": (usage or {}).get("prompt_tokens"),
        "seed": args.seed, "fixture_sha256": fixture_sha,
        "needle_position_fractions": list(needles.values()),
        "ttft_s": round(first, 3) if first else None,
        "wall_s": round(wall, 3),
        "completion_tokens": (usage or {}).get("completion_tokens", len(chunks)),
        "needles_hit": f"{hits}/5", "per_needle": per_needle,
        "PASS": hits == 5, "answer": text[:200],
        "cache_salt": salt,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "needle-result.json"), "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in
                      ("experiment_id", "needles_hit", "PASS", "ttft_s", "wall_s")},
                     ensure_ascii=False))
    return 0 if report["PASS"] else 2


if __name__ == "__main__":
    sys.exit(main())

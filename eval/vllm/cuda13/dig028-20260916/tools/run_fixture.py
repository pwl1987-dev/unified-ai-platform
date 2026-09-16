#!/usr/bin/env python3
"""dig028 fixture runner — 复用 ulmus_validate.benchmark() + /metrics 差分接受率。
用法: run_fixture.py <api:http://127.0.0.1:PORT/v1> <profile> <out.json> [prefill_target=4096]"""
import json
import sys
import urllib.request

sys.path.insert(0, "/data/repos/qwen3.8-27b-8x4090-stack/inference/vllm/bench")
from ulmus_validate import benchmark  # noqa: E402

API, PROFILE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PREFILL = int(sys.argv[4]) if len(sys.argv) > 4 else 4096
KEYS = ("vllm:spec_decode_num_accepted_tokens_total",
        "vllm:spec_decode_num_draft_tokens_total",
        "vllm:spec_decode_num_drafts_total")


def spec_metrics():
    txt = urllib.request.urlopen(API.removesuffix("/v1") + "/metrics", timeout=10).read().decode()
    m, per_pos = {}, {}
    for line in txt.splitlines():
        for k in KEYS:
            if line.startswith(k + " ") or line.startswith(k + "{"):
                parts = line.split()
                m[parts[0].split("{")[0].replace("vllm:", "")] = float(parts[-1])
        if line.startswith("vllm:spec_decode_num_accepted_tokens_per_pos_total{"):
            pos = line.split('position="')[1].split('"')[0]
            per_pos[pos] = float(line.split()[-1])
    if per_pos:
        m["accepted_per_pos"] = per_pos
    return m


before = spec_metrics()
bench = benchmark(API, "qwen3.8-27b", prefill_target=PREFILL)
after = spec_metrics()
delta = {}
for k in set(before) | set(after):
    bv, av = before.get(k, {} if k == "accepted_per_pos" else 0.0), after.get(k, {} if k == "accepted_per_pos" else 0.0)
    if k == "accepted_per_pos":
        delta[k] = {p: round(av.get(p, 0.0) - bv.get(p, 0.0)) for p in set(bv) | set(av)}
    else:
        delta[k] = round(av - bv)
report = {"profile": PROFILE, "benchmark": bench,
          "spec_before": before, "spec_after": after, "spec_delta": delta}
with open(OUT, "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
d = bench["decode_rows"]
acc = (delta.get("num_accepted_tokens_total", 0) /
       max(1, delta.get("num_draft_tokens_total", 0)))
print(json.dumps({
    "decode_median_tok_s": round(bench["decode_tok_s_median"], 4),
    "rows": [round(r["decode_tok_s"], 4) for r in d],
    "prompt_tokens": d[0]["prompt_tokens"],
    "completion_tokens": [r["completion_tokens"] for r in d],
    "prefill_tok_s": (bench.get("prefill") or {}).get("prefill_tok_s"),
    "acceptance_pct": round(100 * acc, 2),
    "spec_delta": delta,
}, indent=1))

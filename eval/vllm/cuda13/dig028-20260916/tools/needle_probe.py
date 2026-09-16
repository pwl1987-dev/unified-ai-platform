#!/usr/bin/env python3
"""长上下文 5-needle 精度探针（非模式化随机值，参照 09-16 v2 协议）。
用法: needle_probe.py <api> <profile> <out.json> <prompt_tokens>"""
import json
import random
import sys
import time
import urllib.request

sys.path.insert(0, "/data/repos/qwen3.8-27b-8x4090-stack/inference/vllm/bench")
from ulmus_validate import make_prompt  # noqa: E402

API, PROFILE, OUT, NTOK = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
rng = random.Random(99)
base = make_prompt(NTOK)
# 按 10/30/50/70/90% 深度插入 5 个随机 6 位码
lines = base.split("\n")
needles = {}
for frac in (0.1, 0.3, 0.5, 0.7, 0.9):
    code = f"{rng.randint(100000, 999999)}"
    needles[code] = frac
    pos = int(len(lines) * frac)
    lines.insert(pos, f"登记码 {code} 已备案，请记住。")
doc = "\n".join(lines)
q = ("以上文档中出现了五个'登记码'，请只输出这五个六位数字，用逗号分隔，"
     "不要输出其他内容。")
payload = {
    "model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
    "chat_template_kwargs": {"enable_thinking": False},
    "messages": [{"role": "user", "content": doc + "\n\n" + q}],
    "max_tokens": 64, "stream": True,
    "stream_options": {"include_usage": True},
    "cache_salt": f"needle-{PROFILE}",
}
req = urllib.request.Request(API + "/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
t0 = time.monotonic()
first, chunks = None, []
with urllib.request.urlopen(req, timeout=900) as r:
    for raw in r:
        line = raw.decode().strip()
        if not line.startswith("data: "):
            continue
        if line[6:] == "[DONE]":
            break
        obj = json.loads(line[6:])
        d = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        if d:
            chunks.append(d)
            if first is None:
                first = time.monotonic() - t0
wall = time.monotonic() - t0
text = "".join(chunks)
hits = sum(1 for c in needles if c in text)
report = {"profile": PROFILE, "prompt_tokens": NTOK, "ttft_s": round(first, 1),
          "wall_s": round(wall, 1), "needles_hit": f"{hits}/5",
          "PASS": hits == 5, "answer_head": text[:80]}
with open(OUT, "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
print(json.dumps(report, ensure_ascii=False))

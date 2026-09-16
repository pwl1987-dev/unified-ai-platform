#!/usr/bin/env python3
"""逐字复述探针 — ngram 投机的主场场景（输出大量复现 prompt 内容）。
用法: probe_verbatim.py <api> <profile> <out.json>"""
import json
import sys
import time
import urllib.request

API, PROFILE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

DISTRICTS = ["兰山", "罗庄", "河东", "沂南", "郯城", "沂水", "兰陵", "费县",
             "平邑", "莒南", "蒙阴", "临沭", "高新区", "经开区", "沂河新区"]
CATS = ["供暖保障", "道路施工", "秋粮收购", "医保服务", "校园安全", "文旅活动",
        "防汛演练", "招商引资", "老旧改造", "就业招聘", "环保督察", "公交调整"]
VERBS = ["推进", "启动", "完成", "部署", "开展", "落实", "组织", "升级"]
SEED_TEXT = "临沂广播电视臺记自基层一线报道"

lines = []
for i in range(1, 101):
    d = DISTRICTS[i % len(DISTRICTS)]
    c = CATS[(i * 7) % len(CATS)]
    v = VERBS[(i * 3) % len(VERBS)]
    day = 1 + (i % 28)
    lines.append(f"【条目{i:03d}】2026-09-{day:02d} {d}区{c}工作专班{v}第{i}批次任务，"
                 f"覆盖{12 + i}个村居社区，服务群众约{300 + i * 17}人次，"
                 f"现场反馈满意度{91 + (i % 8)}%。{SEED_TEXT}。")
doc = "\n".join(lines)

payload = {
    "model": "qwen3.8-27b",
    "temperature": 0,
    "seed": 4242,
    "chat_template_kwargs": {"enable_thinking": False},
    "messages": [{"role": "user",
                  "content": doc + "\n\n请逐字复述以上全部内容，从条目001到条目100，不要添加任何解释。"}],
    "max_tokens": 8192,
    "stream": True,
    "stream_options": {"include_usage": True},
    "cache_salt": "verbatim-" + str(int(time.time())),
}

req = urllib.request.Request(API + "/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
t0 = time.monotonic()
chunks, usage = [], None
with urllib.request.urlopen(req, timeout=600) as r:
    for raw in r:
        line = raw.decode().strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        obj = json.loads(data)
        if "usage" in obj and obj["usage"]:
            usage = obj["usage"]
        delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        if delta:
            chunks.append(delta)
wall = time.monotonic() - t0
text = "".join(chunks)
first_ok = lines[0].split("，")[0] in text
last_ok = lines[-1].split("，")[0] in text
ct = (usage or {}).get("completion_tokens", len(chunks))
report = {
    "profile": PROFILE,
    "wall_s": round(wall, 2),
    "completion_tokens": ct,
    "decode_tok_s": round(ct / wall, 1),
    "prompt_report_tokens": (usage or {}).get("prompt_tokens"),
    "first_line_present": first_ok,
    "last_line_present": last_ok,
}
with open(OUT, "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
with open(OUT + ".text", "w") as f:
    f.write(text)
print(json.dumps(report, ensure_ascii=False))
print("HEAD:", text[:100].replace("\n", "|"))

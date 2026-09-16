#!/usr/bin/env python3
"""聚合 torch profiler chrome trace 的 kernel 时间。用法: analyze_trace.py <trace.json.gz>"""
import gzip
import json
import sys
from collections import defaultdict

path = sys.argv[1]
with gzip.open(path, "rt") as f:
    data = json.load(f)

ev = data["traceEvents"] if isinstance(data, dict) else data
kern = defaultdict(lambda: [0, 0])   # name -> [total_us, count]
gpu_total = 0
t_min, t_max = None, None
for e in ev:
    if e.get("ph") != "X":
        continue
    cat = e.get("cat", "")
    if cat in ("kernel", "gpu_memcpy", "gpu_memset"):
        name = e["name"].split("<")[0][:90]
        d = e.get("dur", 0)
        kern[(cat, name)][0] += d
        kern[(cat, name)][1] += 1
        gpu_total += d
        ts = e.get("ts", 0)
        t_min = ts if t_min is None else min(t_min, ts)
        t_max = ts + d if t_max is None else max(t_max, ts + d)

rows = sorted(kern.items(), key=lambda kv: -kv[1][0])
span_s = (t_max - t_min) / 1e6 if t_min is not None else 0
print(f"GPU busy total: {gpu_total/1e6:.2f}s over span {span_s:.2f}s "
      f"(busy率 {100*gpu_total/1e6/max(span_s,1e-9):.0f}%, 含 prefill)")
print(f"{'total_ms':>9} {'count':>7} {'mean_us':>8}  cat/name")
for (cat, name), (tot, cnt) in rows[:28]:
    print(f"{tot/1000:9.1f} {cnt:7d} {tot/cnt:8.1f}  {cat}: {name}")

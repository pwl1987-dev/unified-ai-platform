#!/usr/bin/env python3
"""verbatim 逐字复述夹具 + 五类损坏负例自检（Harness Gate §6.0.6 / v2.1）。

校验器必须能检出：缺首行 / 缺末行 / 行乱序 / 编号格式错误 / 复读环。
任何一类漏检 => Harness Gate 不通过。
证据形态参照 dig028 tools/probe_verbatim.py（100 条结构化新闻体，代码内确定性生成）。

用法:
  verbatim_check.py selftest                 # 只跑负例自检（无 GPU）
  verbatim_check.py probe --api URL --out DIR --experiment-id ID
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request

# 确定性 100 条结构化行（与 dig028 probe_verbatim 同风格：编号+条目）
rng = random.Random(4242)
WORDS = ("新华社", "路透社", "美联社", "法新社", "共同社", "塔斯社", "安莎社", "埃菲社")


def gen_lines(n: int = 100) -> list[str]:
    r = random.Random(4242)
    out = []
    for i in range(1, n + 1):
        w = r.choice(WORDS)
        day = r.randint(1, 28)
        out.append(f"{i:03d}|{w}|{2020 + r.randint(0, 6)}-09-{day:02d}|"
                   f"第{i}号公报称局势稳定，指标{i * 7}点，环比升{r.randint(1, 9)}%。")
    return out


def check_verbatim(expected: list[str], got_lines: list[str]) -> dict:
    """逐行 exact 判定 + 首尾行 + 顺序 + 编号格式 + 复读检测。"""
    res = {
        "first_line_ok": bool(got_lines and got_lines[0].strip() == expected[0].strip()),
        "last_line_ok": bool(got_lines and got_lines[-1].strip() == expected[-1].strip()),
        "line_count": len(got_lines), "expected_count": len(expected),
        "order_ok": True, "numbering_ok": True, "loop_ok": True,
        "exact_lines_ok": 0, "mismatch_examples": [],
    }
    norm = [l.strip() for l in got_lines if l.strip()]
    for i, (e, g) in enumerate(zip(expected, norm)):
        if e != g:
            res["exact_lines_ok"] = res.get("exact_lines_ok", 0)
            if len(res["mismatch_examples"]) < 5:
                res["mismatch_examples"].append({"line": i, "expected": e[:60], "got": g[:60]})
        else:
            res["exact_lines_ok"] += 1
    # 顺序：编号序列须严格递增
    nums = []
    for l in norm:
        m = re.match(r"^(\d+)\|", l)
        nums.append(int(m.group(1)) if m else -1)
    res["order_ok"] = all(b > a for a, b in zip(nums, nums[1:]))
    res["numbering_ok"] = nums == list(range(1, len(expected) + 1))
    # 复读环：相邻同句重复 >=3 次
    dup = 0
    for i in range(2, len(norm)):
        if norm[i] == norm[i - 1] == norm[i - 2]:
            dup += 1
    res["loop_ok"] = dup == 0
    res["loop_repeats"] = dup
    res["PASS"] = (res["first_line_ok"] and res["last_line_ok"]
                   and res["order_ok"] and res["numbering_ok"] and res["loop_ok"]
                   and res["exact_lines_ok"] == len(expected))
    return res


def corrupt(lines: list[str], kind: str) -> list[str]:
    if kind == "drop_first":
        return lines[1:]
    if kind == "drop_last":
        return lines[:-1]
    if kind == "shuffle":
        out = lines[:]
        random.Random(7).shuffle(out)
        return out
    if kind == "numbering":
        out = lines[:]
        out[10] = re.sub(r"^\d+\|", "XX|", out[10])
        return out
    if kind == "loop":
        return lines[:20] + [lines[19]] * 6 + lines[20:]
    raise ValueError(kind)


KINDS = ["drop_first", "drop_last", "shuffle", "numbering", "loop"]


def selftest() -> int:
    lines = gen_lines()
    # 健全性：未损坏必须 PASS
    ok = check_verbatim(lines, lines)
    results = {"intact": {"PASS": ok["PASS"]}}
    all_detected = ok["PASS"]
    for kind in KINDS:
        bad = corrupt(lines, kind)
        r = check_verbatim(lines, bad)
        detected = not r["PASS"]
        results[kind] = {"detected": detected,
                         "first_line_ok": r["first_line_ok"],
                         "last_line_ok": r["last_line_ok"],
                         "order_ok": r["order_ok"],
                         "numbering_ok": r["numbering_ok"],
                         "loop_ok": r["loop_ok"]}
        all_detected = all_detected and detected
    print(json.dumps(results, indent=1, ensure_ascii=False))
    print("SELFTEST_" + ("PASS" if all_detected else "FAIL"))
    return 0 if all_detected else 1


def probe(args) -> int:
    lines = gen_lines()
    doc = "\n".join(lines)
    payload = {
        "model": "qwen3.8-27b", "temperature": 0, "seed": 4242,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user",
                      "content": doc + "\n\n请逐字复述以上全部内容，从第一行到最后一行，"
                                   "不要增删改任何行，不要输出其他内容。"}],
        "max_tokens": 4096, "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": f"{args.salt_namespace}-verbatim-{args.experiment_id}",
    }
    req = urllib.request.Request(args.api + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic_ns()
    chunks = []
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
    text = "".join(chunks)
    got = [l for l in text.splitlines() if l.strip()]
    report = {"experiment_id": args.experiment_id,
              "wall_s": round((time.monotonic_ns() - t0) / 1e9, 3),
              **check_verbatim(lines, got), "answer_head": text[:120]}
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "verbatim-result.json"), "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("PASS", "exact_lines_ok", "line_count")},
                     ensure_ascii=False))
    return 0 if report["PASS"] else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    p2 = sub.add_parser("probe")
    p2.add_argument("--api", required=True)
    p2.add_argument("--out-dir", required=True)
    p2.add_argument("--experiment-id", required=True)
    p2.add_argument("--salt-namespace", default="formal")
    args = ap.parse_args()
    return selftest() if args.cmd == "selftest" else probe(args)


if __name__ == "__main__":
    sys.exit(main())

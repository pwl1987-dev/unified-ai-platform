#!/usr/bin/env python3
"""夹具生成与 SHA256 冻结（评审 v2.1 第 8 条）。

夹具与 dig028 bench_conc.py / needle_probe.py 同源：make_prompt(target)。
生成物不落 Git（大文本）；落盘 fixtures/manifest.json 记录
name / target_tokens / prompt_sha256 / 生成器 SHA256，供 manifest 引用。

needle 夹具：给定 seed，按 10/30/50/70/90% 百分位插 5 个六位码，
返回完整 prompt 与 needle 码表；码表随 seed 变化，位置百分位固定。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.join(REPO, "inference", "vllm", "bench"))
from ulmus_validate import make_prompt  # noqa: E402

NEEDLE_FRACTIONS = (0.1, 0.3, 0.5, 0.7, 0.9)
NEEDLE_QUESTION = ("以上文档中出现了五个'登记码'，请只输出这五个六位数字，用逗号分隔，"
                   "不要输出其他内容。")


def make_needle_fixture(prompt_tokens: int, seed: int) -> tuple[str, dict]:
    """返回 (完整prompt, {code: position_fraction})。位置百分位固定，码值随 seed。"""
    rng = random.Random(seed)
    base = make_prompt(prompt_tokens)
    lines = base.split("\n")
    needles = {}
    for frac in NEEDLE_FRACTIONS:
        code = f"{rng.randint(100000, 999999)}"
        needles[code] = frac
        pos = int(len(lines) * frac)
        lines.insert(pos, f"登记码 {code} 已备案，请记住。")
    doc = "\n".join(lines)
    return doc + "\n\n" + NEEDLE_QUESTION, needles


def gen_sha_manifest() -> dict:
    out = {"generator": "tools/gen_fixtures.py",
           "generator_sha256": hashlib.sha256(
               open(os.path.abspath(__file__), "rb").read()).hexdigest(),
           "fixtures": {}}
    for name, target in [("d565", 512), ("p4k", 4096), ("p32k", 32768),
                         ("p220k", 220000), ("p238k", 238000)]:
        p = make_prompt(target)
        out["fixtures"][name] = {
            "target_tokens": target,
            "prompt_sha256": hashlib.sha256(p.encode()).hexdigest(),
        }
    # needle 夹具：每 seed 一套（238K 债务用 seed 1..3；220K 锚点用 seed 1）
    for ctx in (220000, 238000):
        for seed in (1, 2, 3):
            doc, needles = make_needle_fixture(ctx, seed)
            out["fixtures"][f"needle-p{ctx//1000}k-s{seed}"] = {
                "target_tokens": ctx, "seed": seed,
                "prompt_sha256": hashlib.sha256(doc.encode()).hexdigest(),
                "needles": needles,
            }
    return out


def main() -> int:
    m = gen_sha_manifest()
    out_path = os.path.join(os.path.dirname(HERE), "fixtures", "manifest.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    print(json.dumps({"written": out_path, "fixtures": list(m["fixtures"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

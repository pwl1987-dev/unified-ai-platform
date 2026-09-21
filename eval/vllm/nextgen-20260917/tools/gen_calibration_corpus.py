#!/usr/bin/env python3
"""Phase 03 P0A.7 — 独立校准语料生成器（与评测集物理隔离）。

契约（gates-phase03 calibration_contract.dataset_isolation）：
  - 不得使用 s99/s2/s5 needle 码集、ccdet、verbatim、Gate C 最终质量集做校准数据
  - 语料与 ulmus FILLER（make_prompt 家族=perf 夹具）不同源：本生成器用独立模板族
  - 确定性（rng seed 20260921，与 needle seeds 99/2/5 无交集）
  - 产出：samples.jsonl + corpus manifest（样本 SHA、聚合 SHA、tokenizer SHA）
校准语义：per-tensor KV absmax scale 收敛只需代表性短中长样本（64 样本、≤8192 token），
不需要 200K 长文（策略参数，进 provenance）。
"""
from __future__ import annotations

import hashlib
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(os.path.dirname(HERE), "fixtures")  # .../nextgen-20260917/fixtures
OUT_DIR = os.path.join(FIX, "calibration", "phase03-corpus")

SEED = 20260921          # 与 needle seeds(99/2/5) 无交集；冻结
N_SAMPLES = 64
MAX_LEN_TOKENS_BUDGET = 8192   # 每样本 token 预算（生成按字符近似，manifest 记录预算）

ZH_TMPL = [
    "本季度{region}电网负荷峰值出现在{hour}时，调度中心记录的最大值约为{num}兆瓦。"
    "值班团队按照预案执行了{n}轮错峰指令，整体频率偏差保持在合理区间。",
    "{city}轨道交通线网昨日客流量达到{num}万人次，其中换乘站贡献了约三分之一。"
    "运营方表示将根据{hour}时段的拥挤度动态调整发车间隔。",
    "研究团队在{num}份样本中观察到该指标的缓慢漂移，统计显著性处于边界。"
    "作者建议在{region}范围内复核抽样框，并报告分层后的效应量。",
]
EN_TMPL = [
    "The pipeline ingests {num} events per second and persists them to a columnar store. "
    "During the {hour} peak, backpressure propagates to the encoder stage within seconds.",
    "We benchmarked {n} configurations on identical hardware. Variance across runs stayed "
    "below one percent once caches were warm, so the ranking is stable.",
    "The reviewer asked whether the {num}-token context window changes retrieval behavior. "
    "Our ablation keeps the prompt fixed and varies only the cache representation.",
]
CODE_TMPL = [
    "def merge_intervals(spans):\n    spans = sorted(spans)\n    out = []\n"
    "    for s, e in spans:\n        if out and s <= out[-1][1] + {num}:\n"
    "            out[-1] = (out[-1][0], max(out[-1][1], e))\n        else:\n"
    "            out.append((s, e))\n    return out\n",
    "class Ring{N}Buffer:\n    def __init__(self, cap={num}):\n"
    "        self.cap = cap; self.buf = [None] * cap; self.i = 0\n"
    "    def push(self, v):\n        self.buf[self.i] = v; self.i = (self.i + 1) % self.cap\n",
]
JSON_TMPL = [
    '{{"tool": "calendar.lookup", "args": {{"month": {m}, "day": {d}}}, '
    '"id": "call-{num:06d}", "strict": true}}',
    '{{"status": "ok", "count": {num}, "items": [{{"k": "v{n}"}}, {{"k": "v{n}2"}}], '
    '"cursor": null}}',
]
DOMAINS = [("zh", ZH_TMPL), ("en", EN_TMPL), ("code", CODE_TMPL), ("tool_json", JSON_TMPL)]


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def build_samples() -> list[dict]:
    rng = random.Random(SEED)
    samples = []
    for i in range(N_SAMPLES):
        dom, tmpls = DOMAINS[i % len(DOMAINS)]
        target_chars = 1200 + (i * 137) % 6800          # 混合短中长，确定性
        parts, acc = [], 0
        while acc < target_chars:
            t = rng.choice(tmpls)
            seg = t.format(region=rng.choice(["华东", "华南", "西南", "华北"]),
                           city=rng.choice(["临港", "滨江", "科学城", "老城"]),
                           hour=rng.randrange(8, 22), num=rng.randrange(1000, 99999),
                           n=rng.randrange(2, 97), N=rng.choice(["", "X"]),
                           m=rng.randrange(1, 12), d=rng.randrange(1, 28))
            parts.append(seg)
            acc += len(seg)
        text = "\n".join(parts)
        samples.append({"id": f"cal-{i:03d}", "domain": dom, "text": text,
                        "sha256": _sha(text)})
    return samples


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    samples = build_samples()
    with open(os.path.join(OUT_DIR, "samples.jsonl"), "w") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    agg = hashlib.sha256(
        "\n".join(s["sha256"] for s in samples).encode()).hexdigest()
    manifest = {
        "purpose": "Phase 03 FP8C 校准语料（独立于全部评测集；gates calibration_contract）",
        "generator": "tools/gen_calibration_corpus.py",
        "generator_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
        "seed": SEED, "sample_count": len(samples),
        "max_len_tokens_budget": MAX_LEN_TOKENS_BUDGET,
        "dataset_sha256": agg,
        "sample_ids_and_hashes": [{"id": s["id"], "sha256": s["sha256"]}
                                  for s in samples],
        "forbidden_usage_check": "不含 needle 码集（s99/s2/s5 六位码）/ccdet/verbatim/评测 fixture 文本",
        "tokenizer_sha256_to_bind": "由 FP8C 构建时写入 provenance（calibration_provenance.tokenizer_sha256）",
    }
    with open(os.path.join(FIX, "calibration", "phase03-corpus-manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps({"samples": len(samples), "dataset_sha256": agg,
                      "out": OUT_DIR}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

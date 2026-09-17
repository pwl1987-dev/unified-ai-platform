#!/usr/bin/env python3
"""P1 fixture 判别探针（NOT_ATTRIBUTABLE_TO_KVARN 分支的最小闭环）。

背景：2×2 屏蔽四臂全 2/5，bf16 与 kvarn 输出逐字节相同（941235,900875）。
生成器同源同问句，唯一差异=RNG seed（dig028 历史通过用 seed=99；Phase 00 用 1/2/3）。

探针（target-only 双 dtype，各 1 boot）：
  bf16 SD0：seed99@220K（dig028 码集复测）、seed2@220K（nextgen 已知可召回码集）、seed1@128K（长度剖面）
  kvarn SD0：seed99@220K（跨 dtype 确认）
判定：
  seed99 5/5（双 dtype）→ 码集依赖确证，220K needle 门以 seed99 为参考协议复活
  seed1@128K 5/5 → 失败随长度涌现（128K→220K 之间）；2/5 → 码集本身不可召回（夹具问题）
"""
from __future__ import annotations

import json
import os
import sys

from p1_causal import SBX, STAGING, boot, needle, stop, thermal_wait  # noqa: E402
from gen_fixtures import make_needle_fixture  # noqa: E402

OUT_FILE = os.path.join(STAGING, "P1-CAUSAL", "p1-fixture-discrim.json")


def probe(kv_label: str, dtype: str, ml: int, runs: list[tuple[int, int]]) -> list[dict]:
    ready, pgid, log = boot(f"p1fd-{kv_label.lower()}", dtype, ml, spec=0)
    if not ready:
        return [{"boot_ready": False, "log": log}]
    thermal_wait()
    out = []
    for seed, pt in runs:
        exp = f"V28-T2-Q0-{kv_label}-SD0-MS1-NBT2048-C1-L{pt // 1000}K-P1FD-S{seed}"
        nr = needle(exp, pt, seed)
        _, needles = make_needle_fixture(pt, seed)
        nr["needle_codes"] = needles
        out.append({"seed": seed, "prompt_tokens": pt, "PASS": nr.get("PASS"),
                    "hits": nr.get("needles_hit"), "answer": nr.get("answer_head"),
                    "codes": needles})
        print(json.dumps({"kv": kv_label, "seed": seed, "pt": pt,
                          "PASS": nr.get("PASS"), "hits": nr.get("needles_hit"),
                          "answer": (nr.get("answer_head") or "")[:60]}), flush=True)
    stop(pgid)
    return out


def main() -> int:
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    if "kvb16" not in doc:
        doc["kvb16"] = probe("KVB16", "bfloat16", 225280,
                             [(99, 220000), (2, 220000), (1, 128000)])
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
    if "kvarn" not in doc:
        doc["kvarn"] = probe("KVARN", "kvarn_k4v2_g128", 225280,
                             [(99, 220000)])
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
    # 判定
    def hit(arm, seed):
        return [r for r in doc.get(arm, []) if r.get("seed") == seed]
    s99 = [r.get("PASS") for r in hit("kvb16", 99)] + [r.get("PASS") for r in hit("kvarn", 99)]
    s2 = [r.get("PASS") for r in hit("kvb16", 2)]
    s128 = [r.get("PASS") for r in hit("kvb16", 1)]
    doc["verdict"] = {
        "seed99_recallable_both_dtypes": all(s99) if s99 else None,
        "seed2_220k_recallable": all(s2) if s2 else None,
        "seed1_128k": s128[0] if s128 else None,
        "conclusion_rule": {
            "seed99_pass+seed1_128k_pass": "码集依赖 + 长度涌现（128→220K 间召回塌陷）",
            "seed99_pass+seed1_128k_fail": "码集依赖（seed1 码集本身不可召回=夹具问题）",
            "seed99_fail": "220K 全面召回退化（与码集无关）——升级为模型长上下文质量问题",
        },
    }
    json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(doc["verdict"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

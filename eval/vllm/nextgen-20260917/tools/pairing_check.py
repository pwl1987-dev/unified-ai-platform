#!/usr/bin/env python3
"""TP1/TP2 配对检查器（v2.1 第 5 条 / MASTER §2.2）。

正式差值计算前核对两侧：
  fixture_sha256 / actual_input_tokens / requested_output_tokens / stop_condition
  / sampling(seed,temp,ignore_eos) / cache_salt_namespace / client_version
任一不同 => UNPAIRED_OBSERVATION，不得进入正式加速比。

用法: pairing_check.py <exp-dir-A> <exp-dir-B>
"""
from __future__ import annotations

import json
import os
import sys


def load(exp_dir: str) -> dict:
    m = json.load(open(os.path.join(exp_dir, "metrics.json")))
    mf = json.load(open(os.path.join(exp_dir, "manifest.json")))
    # 取第一条 raw 记录的采样与 fixture 身份（同 run 内一致）
    first = None
    with open(os.path.join(exp_dir, "raw-events.jsonl")) as f:
        for ln in f:
            if ln.strip():
                first = json.loads(ln)
                break
    return {
        "fixture_sha256": m.get("fixture_sha256"),
        "fixture_name": m.get("fixture_name"),
        "actual_input_tokens": (first or {}).get("fixture", {}).get("actual_input_tokens"),
        "requested_output_tokens": m.get("requested_output_tokens"),
        "mode": m.get("mode"),
        "seed": (first or {}).get("sampling", {}).get("seed"),
        "temperature": (first or {}).get("sampling", {}).get("temperature"),
        "ignore_eos": (first or {}).get("sampling", {}).get("ignore_eos"),
        "enable_thinking": (first or {}).get("sampling", {}).get("enable_thinking"),
        "cache_salt_namespace": (first or {}).get("cache_salt_namespace"),
        "client_version": m.get("client_version"),
        "harness_git_sha": mf.get("harness_git_sha"),
    }


PAIR_KEYS = ["fixture_sha256", "actual_input_tokens", "requested_output_tokens",
             "mode", "seed", "temperature", "ignore_eos", "enable_thinking",
             "cache_salt_namespace", "client_version", "harness_git_sha"]


def main() -> int:
    a, b = load(sys.argv[1]), load(sys.argv[2])
    diffs = {k: [a.get(k), b.get(k)] for k in PAIR_KEYS if a.get(k) != b.get(k)}
    result = {"paired": not diffs, "diffs": diffs,
              "verdict": "PAIRED" if not diffs else "UNPAIRED_OBSERVATION"}
    print(json.dumps(result, indent=1, ensure_ascii=False))
    # PAIRED 时输出正式差值所需字段
    if not diffs:
        for side, d in (("A", sys.argv[1]), ("B", sys.argv[2])):
            m = json.load(open(os.path.join(d, "metrics.json")))
            pr = [r for r in m["per_request"] if r["ok"] and not r["early_stop"]]
            result[f"side_{side}"] = {
                "client_observed_decode_tok_s": [r["client_observed_decode_tok_s"] for r in pr],
                "e2e_output_tok_s": [r["e2e_output_tok_s"] for r in pr],
                "output_tokens": [r["output_tokens"] for r in pr],
            }
        with open(os.path.join(os.path.dirname(sys.argv[1]), "pairing.json"), "w") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
    return 0 if not diffs else 2


if __name__ == "__main__":
    sys.exit(main())

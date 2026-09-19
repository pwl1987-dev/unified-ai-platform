#!/usr/bin/env python3
"""P2 dynamic-k 阶梯评估 — K5/K6/TONLY/K8CHECK vs K7 参照（PAIR34 P32K / B0-L32 D565）。

证据源：raw/staging/<run>/sampler-metrics.jsonl 的 vllm:spec_decode_* 计数器首末差
（每 rep 一个窗口，臂级聚合 = 各 rep delta 求和）。

解析纪律（同 p02_common）：
- 计数器只认精确族名 `vllm:spec_decode_<name>_total`；`_created`（epoch 秒表）一律排除；
- per-pos 族带 position 标签，按 (族名, position) 精确匹配；
- 自洽校验：sum(per_pos deltas) == accepted delta，偏差 >0.1% 记 PARSE_INCONSISTENT。

接受率定义（对齐 gates-phase02.yaml dynamic_k.acceptance_gate）：
- total_acceptance = accepted / proposed（proposed = draft_tokens）
- pos_rate[i]  = accepted_pos_i / drafts          （草稿步到达且接受第 i 位的比例）
- cond[i]      = accepted_pos_i / accepted_pos_{i-1}（条件接受率）
- per_position_gap = max 相邻 cond[i] 降幅（pp）——地板 8pp

质量线：verbatim 探针（Tier-A 确定性）；K vs TONLY 逐 token diff 需输出文本，
staging 未存 per-request 文本 → evidence_quality=PARTIAL（口径如实记录）。
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
STAGING = os.path.join(NEXTGEN, "raw", "staging")

FAM = {
    "drafts": "vllm:spec_decode_num_drafts_total",
    "proposed": "vllm:spec_decode_num_draft_tokens_total",
    "accepted": "vllm:spec_decode_num_accepted_tokens_total",
}
FAM_POS = "vllm:spec_decode_num_accepted_tokens_per_pos_total"


def parse_spec_lines(lines: list[str]) -> dict:
    out: dict = {"pos": {}}
    for ln in lines:
        if not ln.startswith("vllm:"):
            continue
        body = ln.split(" ", 1)
        if len(body) != 2:
            continue
        head, val = body
        try:
            v = float(val)
        except ValueError:
            continue
        if head.endswith("_created"):  # 防线 1：epoch 秒表排除
            continue
        if "{" in head:
            fam, labels = head.split("{", 1)
            labels = labels.rstrip("}")
            if fam == FAM_POS:  # per-pos：按 position 标签精确匹配
                for kv in labels.split(","):
                    if kv.startswith('position="') and kv.endswith('"'):
                        try:
                            out["pos"][int(kv[len('position="'):-1])] = v
                        except ValueError:
                            pass
                continue
            for key, f in FAM.items():  # 普通计数器族也带 engine/model 标签
                if fam == f:
                    out[key] = v
            continue
        for key, fam in FAM.items():
            if head == fam:  # 精确族名
                out[key] = v
    return out


def run_delta(run_dir: str) -> dict | None:
    path = os.path.join(run_dir, "sampler-metrics.jsonl")
    if not os.path.exists(path):
        gz = path + ".gz"   # >2MB 证据按铁律 gzip 归档
        if not os.path.exists(gz):
            return None
        import gzip
        fh = gzip.open(gz, "rt")
    else:
        fh = open(path)
    first = last = None
    for ln in fh:
        d = json.loads(ln)
        snap = parse_spec_lines(d.get("vllm_lines", []))
        if "drafts" not in snap:
            continue
        if first is None:
            first = snap
        last = snap
    fh.close()
    if first is None or last is None:
        return None
    delta = {k: last.get(k, 0.0) - first.get(k, 0.0) for k in FAM}
    delta["pos"] = {i: last["pos"].get(i, 0.0) - first["pos"].get(i, 0.0)
                    for i in set(first["pos"]) | set(last["pos"])}
    delta["consistency_ok"] = abs(sum(delta["pos"].values()) - delta["accepted"]) \
        <= max(0.001 * max(delta["accepted"], 1.0), 1.0)
    return delta


def run_perf(run_dir: str) -> dict:
    m = json.load(open(os.path.join(run_dir, "metrics.json")))
    ok = [r for r in m["per_request"] if r["ok"] and not r["early_stop"]]
    dec = [r["client_observed_decode_tok_s"] for r in ok
           if r.get("client_observed_decode_tok_s") is not None]
    ttft = [r["ttft_s"] for r in ok if r.get("ttft_s") is not None]
    wall = sum((r["e2e_latency_s"] - r["ttft_s"]) for r in ok)
    return {
        "requests_ok": m["requests_ok"],
        "http_errors": m["http_errors"],
        "sum_output_tokens": m["aggregate"].get("sum_output_tokens"),
        "agg_tok_s": m["aggregate"].get("aggregate_output_tok_s"),
        "decode_med": round(statistics.median(dec), 3) if dec else None,
        "ttft_med": round(statistics.median(ttft), 4) if ttft else None,
        "decode_wall_s": round(wall, 3),
    }


def arm_cell(prefix_pat: str) -> list[str]:
    return sorted(glob.glob(os.path.join(STAGING, prefix_pat)))


def collect(label: str, prefix_pat: str) -> dict:
    runs = arm_cell(prefix_pat)
    deltas, perfs = [], []
    for d in runs:
        dl = run_delta(d)
        pf = run_perf(d)
        if dl:
            deltas.append(dl)
        perfs.append({"run": os.path.basename(d), **pf})
    out = {"label": label, "n_runs": len(runs), "perf": perfs}
    if deltas:
        tot = {k: sum(x[k] for x in deltas) for k in FAM}
        pos_tot: dict[int, float] = {}
        for x in deltas:
            for i, v in x["pos"].items():
                pos_tot[i] = pos_tot.get(i, 0.0) + v
        k = max(pos_tot) + 1 if pos_tot else None
        acc = {
            "drafts": tot["drafts"],
            "proposed": tot["proposed"],
            "accepted": tot["accepted"],
            "total_acceptance": round(tot["accepted"] / tot["proposed"], 4)
            if tot["proposed"] else None,
            "accepted_per_draft": round(tot["accepted"] / tot["drafts"], 4)
            if tot["drafts"] else None,
            "pos_accepted": {i: int(v) for i, v in sorted(pos_tot.items())},
            "pos_rate": {i: round(v / tot["drafts"], 4) for i, v in sorted(pos_tot.items())},
            "consistency_all_ok": all(x["consistency_ok"] for x in deltas),
        }
        cond = {}
        prev = None
        for i in sorted(pos_tot):
            if prev is not None and pos_tot[prev] > 0:
                cond[i] = round(pos_tot[i] / pos_tot[prev], 4)
            prev = i
        acc["cond_rate"] = cond
        drops = [round((cond[a] - cond[b]) * 100, 2)
                 for a, b in zip(sorted(cond), sorted(cond)[1:])]
        acc["max_adjacent_cond_drop_pp"] = max(drops) if drops else None
        # 发射 token 交叉校验：emitted ≈ accepted + drafts（bonus/步）
        emitted_est = tot["accepted"] + tot["drafts"]
        client_tokens = sum(p.get("sum_output_tokens") or 0 for p in perfs)
        acc["emitted_vs_client_tokens"] = {
            "emitted_est": emitted_est, "client": client_tokens,
            "ratio": round(emitted_est / client_tokens, 4) if client_tokens else None}
        out["acceptance"] = acc
    return out


def med(items: list, key: str):
    vals = [x[key] for x in items if x.get(key) is not None]
    return round(statistics.median(vals), 3) if vals else None


def main() -> int:
    # 臂 → cell 目录模式（k7 参照：PAIR34 P32K 同配方单 boot + B0-L32 D565 3-boot）
    cells = [
        ("K5-D565", "V29-T2-SCR-K5-C1-L0565-F512-B01-R*"),
        ("K5-P32K", "V29-T2-SCR-K5-C1-L032K-NS-B01-R*"),
        ("K6-D565", "V29-T2-SCR-K6-C1-L0565-F512-B01-R*"),
        ("K6-P32K", "V29-T2-SCR-K6-C1-L032K-NS-B01-R*"),
        ("TONLY-D565", "V29-T2-SCR-TONLY-C1-L0565-F512-B01-R*"),
        ("TONLY-P32K", "V29-T2-SCR-TONLY-C1-L032K-NS-B01-R*"),
        ("K8-D565", "V29-T2-SCR-K8-C1-L0565-F512-B01-R*"),
        ("K7-PAIR34-D565", "V29-T2-PAIR34-KVBF16-SD7-MS4-NBT2048-L36K-C1-L0565-F512-B01-R*"),
        ("K7-PAIR34-P32K", "V29-T2-PAIR34-KVBF16-SD7-MS4-NBT2048-L36K-C1-L032K-NS-B01-R*"),
        ("K7-B0L32-D565", "V29-T2-Q0-KVBF16-SD7-MS4-NBT2048-L36K-C1-L0565-F512-B0*-R*"),
    ]
    out = {"record": "P2-DYNK 阶梯评估", "cells": {}}
    for label, pat in cells:
        out["cells"][label] = collect(label, pat)

    # 汇总表：每臂 decode/agg 中位数 + 接受率 + vs TONLY / K7 提速比
    summ = {}
    for label, c in out["cells"].items():
        perf = c["perf"]
        summ[label] = {
            "n": c["n_runs"],
            "decode_med": med(perf, "decode_med"),
            "agg_med": med(perf, "agg_tok_s"),
            "ttft_med": med(perf, "ttft_med"),
            **({"total_acceptance": c["acceptance"]["total_acceptance"],
                "accepted_per_draft": c["acceptance"]["accepted_per_draft"],
                "pos_rate": c["acceptance"]["pos_rate"],
                "max_adj_cond_drop_pp": c["acceptance"]["max_adjacent_cond_drop_pp"]}
               if "acceptance" in c else {}),
        }
    for arm, ref in [("K5", "TONLY"), ("K6", "TONLY"), ("K8", "TONLY")]:
        for fx in ("D565", "P32K"):
            a, b = summ.get(f"{arm}-{fx}"), summ.get(f"{ref}-{fx}")
            if a and b and a["decode_med"] and b["decode_med"]:
                summ[f"{arm}-{fx}"]["speedup_vs_tonly"] = round(
                    a["decode_med"] / b["decode_med"], 4)
    out["summary"] = summ

    dest = os.path.join(STAGING, "P02-SCREEN", "p2-dynk-eval.json")
    json.dump(out, open(dest, "w"), indent=1, ensure_ascii=False)
    print(f"written {dest}")
    print(json.dumps(summ, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

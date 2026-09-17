#!/usr/bin/env python3
"""P1.2 完整矩阵 — 计划 v1.2（Qualify 口径：3 真独立 boot）。

臂（0.28 栈 TP2，同 overlay 同形制）：
  KVARN-SD7 @220K  对照臂：补 Phase 00 跨 boot 债（frozen negative-control + expanded 3-seed）
  KVB16-SD7 @L     候选臂：每 seed 每 boot 5/5 才 PASS（L=p1-capacity 的 BF16 可行点）
  KVF8-SD7 @220K   诊断臂（FP8_DIAGNOSTIC，scale=1.0，不进 Gate A-X 资格）
每 boot：3 seeds（正确性，5 针/次）+ seed1 ×2 追加 reps（TTFT 口径：同 fixture/seed 3 reps）。
TTFT 注册为 0.29 Gate A-X 的 same-KV reference。
断点续跑：per-arm per-boot per-seed 文件存在即跳过。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

from p1_causal import (LADDER, SBX, STAGING, boot, needle, next_bootno,  # noqa: E402
                       stop, thermal_wait)

CAP_FILE = os.path.join(STAGING, "P1-CAUSAL", "p1-capacity.json")
OUT_FILE = os.path.join(STAGING, "P1-MATRIX", "p1-matrix-report.json")
BOOTS = ("B01", "B02", "B03")
SEEDS = (1, 2, 3)
REF_SEED = 99   # 2×2 屏蔽后新增：dig028 历史可召回参考码集（码集依赖判据的阳性对照）
PORT = 19702
PY = "/data/tools/vllm28-env/bin/python"
HERE = os.path.dirname(os.path.abspath(__file__))


def arm_bootno_global() -> None:
    next_bootno()  # 保证矩阵阶段 boot 号与 screen 阶段不重（唯一 B 号/boot）


def run_arm(arm: str, kv: str, pt: int, ml: int, kv_mem: str, spec: int = 1) -> dict:
    """3 boots × (3 seeds + 2 seed1 追加 reps)。逐项落盘，可断点续跑。"""
    out: dict = {"kv": kv, "prompt_tokens": pt, "boots": {}}
    for b in BOOTS:
        per_seed, ttft_reps = {}, []
        for seed in SEEDS:
            exp = f"V28-T2-Q0-{arm}-SD{spec}-MS1-NBT2048-C1-L{pt // 1000}K-P1M-{b}-S{seed}"
            per_seed[str(seed)] = needle(exp, pt, seed)
            print(json.dumps({"arm": arm, "boot": b, "seed": seed,
                              "PASS": per_seed[str(seed)].get("PASS"),
                              "hits": per_seed[str(seed)].get("needles_hit"),
                              "ttft": per_seed[str(seed)].get("ttft_s")}), flush=True)
            time.sleep(5)
        # TTFT 口径：seed1 同 fixture ×3（S1 已测，补 R2/R3）
        reps = [per_seed["1"].get("ttft_s")]
        for r in (2, 3):
            exp = f"V28-T2-Q0-{arm}-SD{spec}-MS1-NBT2048-C1-L{pt // 1000}K-P1M-{b}-S1R{r}"
            nr = needle(exp, pt, 1)
            reps.append(nr.get("ttft_s"))
            ttft_reps.append(nr)
        out["boots"][b] = {"seeds": per_seed, "ttft_seed1_reps_s": reps,
                           "ttft_median_s": (statistics.median([x for x in reps if x])
                                             if any(reps) else None)}
        _persist(out, arm)
    return out


def _persist(out: dict, arm: str) -> None:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    doc[arm] = out
    json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)


def boot_and_run(arm: str, kv: str, pt: int, ml: int, kv_mem: str, spec: int = 1) -> dict:
    """一个 boot 内跑完 3 seeds + 2 reps（同 boot 的全部证据）。"""
    result: dict = {"kv": kv, "prompt_tokens": pt, "boots": {}}
    prev = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    if arm in prev:
        result = prev[arm]
    for b in BOOTS:
        if b in result.get("boots", {}) and result["boots"][b].get("ttft_median_s") is not None:
            print(f"[{arm}-{b}] evidence present, skip", flush=True)
            continue
        ready, pgid, log = boot(f"p1m-{arm.lower()}", kv, ml, spec, kv_mem=kv_mem)
        if not ready:
            result["boots"][b] = {"boot_ready": False, "log": log}
            _persist(result, arm)
            print(f"[{arm}-{b}] BOOT FAIL — see {log}", flush=True)
            continue
        thermal_wait()
        sub = run_arm_in_boot(arm, kv, pt, spec, b)
        result["boots"][b] = sub
        _persist(result, arm)
        stop(pgid)
        time.sleep(10)
    return result


def run_arm_in_boot(arm: str, kv: str, pt: int, spec: int, b: str) -> dict:
    import time as _t
    per_seed = {}
    for seed in SEEDS:
        exp = f"V28-T2-Q0-{arm}-SD{spec}-MS1-NBT2048-C1-L{pt // 1000}K-P1M-{b}-S{seed}"
        per_seed[str(seed)] = needle(exp, pt, seed)
        print(json.dumps({"arm": arm, "boot": b, "seed": seed,
                          "PASS": per_seed[str(seed)].get("PASS"),
                          "hits": per_seed[str(seed)].get("needles_hit")}), flush=True)
        _t.sleep(5)
    reps = [per_seed["1"].get("ttft_s")]
    for r in (2, 3):
        exp = f"V28-T2-Q0-{arm}-SD{spec}-MS1-NBT2048-C1-L{pt // 1000}K-P1M-{b}-S1R{r}"
        nr = needle(exp, pt, 1)
        reps.append(nr.get("ttft_s"))
    # seed99 参考码集（阳性对照：历史可召回码集；跨 boot 应稳定 5/5）
    exp99 = f"V28-T2-Q0-{arm}-SD{spec}-MS1-NBT2048-C1-L{pt // 1000}K-P1M-{b}-S99"
    nr99 = needle(exp99, pt, REF_SEED)
    return {"seeds": per_seed, "ttft_seed1_reps_s": reps,
            "seed99_reference": {"PASS": nr99.get("PASS"), "hits": nr99.get("needles_hit")},
            "ttft_median_s": (statistics.median([x for x in reps if x])
                              if any(reps) else None)}


def evaluate(doc: dict) -> dict:
    verdict = {}
    for arm, data in doc.items():
        boots = data.get("boots", {})
        seed_detail = {}
        all_pass = True
        for b, sub in boots.items():
            for s, nr in (sub.get("seeds") or {}).items():
                ok = nr.get("PASS") is True
                seed_detail[f"{b}-S{s}"] = {"PASS": ok, "hits": nr.get("needles_hit"),
                                            "positions_hit": nr.get("positions_hit")}
                all_pass = all_pass and ok
        meds = [sub.get("ttft_median_s") for sub in boots.values()
                if sub.get("ttft_median_s") is not None]
        verdict[arm] = {
            "all_5of5_per_seed_per_boot": all_pass,
            "seed_detail": seed_detail,
            "ttft_median_overall_s": statistics.median(meds) if meds else None,
            "ttft_boot_drift": ((max(meds) - min(meds)) / statistics.median(meds)
                                if len(meds) >= 2 and statistics.median(meds) else None),
            "same_kv_reference_for_029": statistics.median(meds) if meds else None,
        }
    # kvarn 对照臂专用：frozen negative-control（220K S1 必须复现浅层失败）
    k = verdict.get("KVARN")
    if k:
        s1 = [d for key, d in k["seed_detail"].items() if key.endswith("-S1")]
        k["negative_control reproduced"] = any(
            d["PASS"] is False and (d.get("hits") or 0) <= 3 for d in s1)
        k["negative_control_rule"] = "220K S1 ≤3/5 且丢针位于浅层（0.1/0.3/0.5）"
    return verdict


def main() -> int:
    cap = json.load(open(CAP_FILE)) if os.path.exists(CAP_FILE) else {}
    L = cap.get("L_bf16") or {"prompt_tokens": 220000, "model_len": 225280}
    pt_b, ml_b = L["prompt_tokens"], L["model_len"]
    fp8_ok = (cap.get("fp8") or {}).get("ready")
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    # 臂序：对照（补债）→ 候选 → 诊断
    if "KVARN" not in doc:
        doc["KVARN"] = boot_and_run("KVARN", "kvarn_k4v2_g128", 220000, 225280, "4820000000")
    if "KVB16" not in doc:
        doc["KVB16"] = boot_and_run("KVB16", "bfloat16", pt_b, ml_b, "auto")
    if "KVF8" not in doc and fp8_ok:
        doc["KVF8"] = boot_and_run("KVF8", "fp8", 220000, 225280, "auto")
    _persist_doc = doc
    v = evaluate(doc)
    doc["verdict"] = v
    json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(v, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

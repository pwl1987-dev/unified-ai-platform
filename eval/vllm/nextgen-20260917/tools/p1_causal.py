#!/usr/bin/env python3
"""P1 KV 因果 A/B — 计划 v1.2（0.28 认证栈 + overlay，TP2/GPU3+4）。

Stage-1 容量预检（P1.0）：BF16 升序阶梯 boot（无 needle），确定 L_bf16；FP8 单点。
Stage-2 2×2 因果屏蔽（P1.1 Screen）：A=KVARN/SD0 B=KVARN/SD7 C=B16/SD0 D=B16/SD7，
         在 L_bf16 上同长配对、seed=1（已知失败 seed）、5 needle；
         E=FP8/SD7 @220K（FP8_DIAGNOSTIC，容量允许时）。
Stage-3 判定：解释表出因果结论，立即落盘；断点续跑逐臂可恢复。
单变量：同 overlay/PYTHONPATH/env/cache root；仅 kv dtype（+derived kv-mem=auto）与 spec 开关。
boot 计数：每次 boot 唯一 B 号（errata #6），计数器落盘防重置。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
PY = "/data/tools/vllm28-env/bin/python"
PORT = 19702
TP2_UUIDS = "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e"
STAGING = os.path.join(NEXTGEN, "raw", "staging")
CAP_FILE = os.path.join(STAGING, "P1-CAUSAL", "p1-capacity.json")
VERDICT_FILE = os.path.join(STAGING, "P1-CAUSAL", "p1-screen-verdict.json")
BOOTNO_FILE = os.path.join(SBX, "p1-bootno.txt")

# 升序安全阶梯（prompt_tokens, model_len）——不撞墙，从目标往下找第一个可行点
LADDER = [(220000, 225280), (192000, 196608), (160000, 163840), (128000, 131072)]

# 臂标签 -> 实际 serve dtype（ID 用标签，boot 用真值）
DTYPES = {"KVARN": "kvarn_k4v2_g128", "KVB16": "bfloat16", "KVF8": "fp8"}


def next_bootno() -> int:
    n = 0
    if os.path.exists(BOOTNO_FILE):
        try:
            n = int(open(BOOTNO_FILE).read().strip())
        except Exception:  # noqa: BLE001
            n = 0
    n += 1
    open(BOOTNO_FILE, "w").write(str(n))
    return n


def boot(tag: str, kv: str, model_len: int, spec: int, kv_mem: str = "auto",
         timeout_s: int = 1500) -> tuple[bool, int | None, str]:
    """返回 (ready, pgid, logpath)。boot 失败时抓容量/OOM 证据行。"""
    bno = next_bootno()
    log = os.path.join(SBX, f"log-{tag}-B{bno:02d}")
    cmd = (f"cd {HERE} && VLLM_CACHE_ROOT={SBX}/cache-anchors-tp2 "
           f"setsid bash p1_boot028.sh {tag}-B{bno:02d} {PORT} 2 1 "
           f"--kv-dtype {kv} --model-len {model_len} --spec {spec} --kv-mem {kv_mem}"
           f" > {SBX}/boot-{tag}-B{bno:02d}.log 2>&1")
    r = subprocess.run(["bash", "-c", cmd], timeout=timeout_s)
    pidf, pgidf = os.path.join(log, "server.pid"), os.path.join(log, "server.pgid")
    pgid = None
    if os.path.exists(pgidf):
        try:
            pgid = int(open(pgidf).read().strip())
        except Exception:  # noqa: BLE001
            pgid = None
    ready = r.returncode == 0
    return ready, pgid, log


def stop(pgid: int | None) -> None:
    if pgid is None:
        return
    if pgid == os.getpgid(0):
        print(f"[stop] REFUSE kill own pgid {pgid}", flush=True)
        return
    import signal
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(30):
        time.sleep(2)
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    time.sleep(3)


def thermal_wait(timeout_s: int = 600) -> bool:
    t0, ok_since = time.time(), None
    while time.time() - t0 < timeout_s:
        cards = subprocess.run([PY, os.path.join(HERE, "nvml_bind.py"), "snapshot"],
                               capture_output=True, text=True)
        try:
            cs = json.loads(cards.stdout)
            ts = [c["temp_c"] for c in cs if c["uuid"] in TP2_UUIDS.split(",")]
        except Exception:  # noqa: BLE001
            time.sleep(5)
            continue
        if all(25 <= t <= 40 for t in ts):
            ok_since = ok_since or time.time()
            if time.time() - ok_since >= 30:
                return True
        else:
            ok_since = None
        time.sleep(5)
    return False


def boot_evidence_lines(log: str) -> list[str]:
    srv = os.path.join(log, "server.txt")
    if not os.path.exists(srv):
        return []
    hits = []
    for line in open(srv, errors="replace"):
        if any(k in line for k in ("maximum number of tokens", "KV cache", "out of memory",
                                   "OOM", "Available KV cache", "cache_dtype")):
            hits.append(line.strip())
    return hits[-12:]


def needle(exp: str, prompt_tokens: int, seed: int) -> dict:
    out = os.path.join(STAGING, exp)
    os.makedirs(out, exist_ok=True)
    nrf = os.path.join(out, "needle-result.json")
    if os.path.exists(nrf):
        return json.load(open(nrf))
    r = subprocess.run([PY, os.path.join(HERE, "needle_probe_nextgen.py"),
                        "--api", f"http://127.0.0.1:{PORT}/v1",
                        "--prompt-tokens", str(prompt_tokens), "--seed", str(seed),
                        "--experiment-id", exp, "--out-dir", out,
                        "--gpu-uuids", TP2_UUIDS],
                       capture_output=True, text=True, timeout=1800)
    try:
        return json.load(open(nrf))
    except Exception:  # noqa: BLE001
        return {"PASS": False, "error": (r.stdout[-300:] + r.stderr[-300:])}


def stage1_capacity() -> dict:
    """BF16 阶梯 + FP8 单点。证据立即落盘 CAP_FILE（断点续跑）。"""
    if os.path.exists(CAP_FILE):
        return json.load(open(CAP_FILE))
    os.makedirs(os.path.dirname(CAP_FILE), exist_ok=True)
    cap = {"bf16_ladder": [], "fp8": None}
    for pt, ml in LADDER:
        ready, pgid, log = boot("p1cap-b16", "bfloat16", ml, spec=0)
        ev = boot_evidence_lines(log)
        cap["bf16_ladder"].append({"prompt_tokens": pt, "model_len": ml, "ready": ready,
                                   "log": log, "evidence": ev})
        json.dump(cap, open(CAP_FILE, "w"), indent=1, ensure_ascii=False)
        if ready:
            cap["L_bf16"] = {"prompt_tokens": pt, "model_len": ml}
            json.dump(cap, open(CAP_FILE, "w"), indent=1, ensure_ascii=False)
            stop(pgid)
            time.sleep(10)
            break
        time.sleep(10)
    ready, pgid, log = boot("p1cap-fp8", "fp8", 225280, spec=0)
    cap["fp8"] = {"prompt_tokens": 220000, "model_len": 225280, "ready": ready,
                  "log": log, "evidence": boot_evidence_lines(log)}
    if ready:
        cap["fp8"]["L"] = {"prompt_tokens": 220000, "model_len": 225280}
        stop(pgid)
        time.sleep(10)
    json.dump(cap, open(CAP_FILE, "w"), indent=1, ensure_ascii=False)
    return cap


def stage2_screen(L: dict) -> dict:
    """2×2 + FP8 诊断臂。L = {'prompt_tokens': N, 'model_len': M}（BF16 可行点）。"""
    pt, ml = L["prompt_tokens"], L["model_len"]
    pt220, ml220 = LADDER[0]
    arms = [
        ("A", "KVARN", 0, pt, ml, "4820000000"),   # kvarn 用冻结显式预算
        ("B", "KVARN", 1, pt, ml, "4820000000"),
        ("C", "KVB16", 0, pt, ml, "auto"),
        ("D", "KVB16", 1, pt, ml, "auto"),
    ]
    if pt != pt220:
        # BF16 装不下 220K 时，220K 上的 Phase 00 负证据不丢：B 臂在 220K 复现一次
        arms.append(("B220", "KVARN", 1, pt220, ml220, "4820000000"))
    res = {}
    for arm, kv, spec, p, m, mem in arms:
        exp = f"V28-T2-Q0-{kv}-SD{spec}-MS1-NBT2048-C1-L{p // 1000}K-P1SCN-{arm}-S1"
        nrf = os.path.join(STAGING, exp, "needle-result.json")
        if os.path.exists(nrf):
            res[arm] = json.load(open(nrf))
            print(json.dumps({"arm": arm, "resumed": True, "PASS": res[arm].get("PASS"),
                              "hits": res[arm].get("needles_hit")}), flush=True)
            continue
        ready, pgid, log = boot(f"p1scn-{arm.lower()}", DTYPES[kv], m, spec, kv_mem=mem)
        os.makedirs(os.path.join(STAGING, exp), exist_ok=True)
        if not ready:
            res[arm] = {"PASS": None, "boot_ready": False, "log": log,
                        "evidence": boot_evidence_lines(log)}
            json.dump(res[arm], open(os.path.join(STAGING, exp, "boot-fail.json"), "w"),
                      indent=1, ensure_ascii=False)
            continue
        thermal_wait()
        nr = needle(exp, p, 1)
        res[arm] = nr
        print(json.dumps({"arm": arm, "PASS": nr.get("PASS"),
                          "hits": nr.get("needles_hit"), "ttft": nr.get("ttft_s")}), flush=True)
        stop(pgid)
        time.sleep(10)
        # P220K 类臂后 re-thermal（thermal 协议）在下一 arm boot 前自然满足
    return res


def verdict(cap: dict, res: dict) -> dict:
    def ok(a):
        r = res.get(a) or {}
        return r.get("PASS") is True
    def fail(a):
        r = res.get(a) or {}
        return r.get("PASS") is False
    A, C, B, D = ok("A"), ok("C"), ok("B"), ok("D")
    if not A and C:
        interp = "KVAR_MAIN_EFFECT"
    elif A and C and not B and D:
        interp = "KVAR_X_SPEC_INTERACTION"
    elif A and C and not B and not D:
        interp = "SPECULATIVE_MAIN_EFFECT"
    elif not A and not C:
        interp = "NOT_ATTRIBUTABLE_TO_KVARN"
    else:
        interp = "UNRESOLVED_MIXED"
    return {
        "cells": {a: {"PASS": (res.get(a) or {}).get("PASS"),
                      "hits": (res.get(a) or {}).get("needles_hit")} for a in res},
        "L_bf16": cap.get("L_bf16"),
        "fp8_220k_ready": (cap.get("fp8") or {}).get("ready"),
        "fp8_arm_PASS": (res.get("E") or {}).get("PASS") if "E" in res else None,
        "interpretation": interp,
        "rule": "A=fail,C=pass→主效应；A,C=pass,B=fail,D=pass→交互；A,C=pass,B,D=fail→spec 主效应；A,C=fail→不可归因",
    }


def main() -> int:
    print("[p1] stage1: capacity ladder", flush=True)
    cap = stage1_capacity()
    print(json.dumps({k: cap[k] for k in ("L_bf16", "fp8") if k in cap},
                     ensure_ascii=False, default=str), flush=True)
    L = cap.get("L_bf16")
    if not L:
        print("[p1] BF16 全阶梯不可行（128K 也装不下）— 记 CAPACITY_LIMIT，转 fp8 诊断", flush=True)
        L = {"prompt_tokens": 128000, "model_len": 131072}  # 2×2 仍在 128K 做同长配对
    print(f"[p1] stage2: 2x2 screen at L={L}", flush=True)
    res = stage2_screen(L)
    # FP8 诊断臂（容量允许且未跑过）
    if (cap.get("fp8") or {}).get("ready"):
        exp = "V28-T2-Q0-KVF8-SD7-MS1-NBT2048-C1-L220K-P1SCN-E-S1"
        if not os.path.exists(os.path.join(STAGING, exp, "needle-result.json")):
            ready, pgid, log = boot("p1scn-e", "fp8", 225280, 1)
            if ready:
                thermal_wait()
                res["E"] = needle(exp, 220000, 1)
                print(json.dumps({"arm": "E(FP8_DIAGNOSTIC)", "PASS": res["E"].get("PASS"),
                                  "hits": res["E"].get("needles_hit")}), flush=True)
                stop(pgid)
                time.sleep(10)
        else:
            res["E"] = json.load(open(os.path.join(STAGING, exp, "needle-result.json")))
    v = verdict(cap, res)
    os.makedirs(os.path.dirname(VERDICT_FILE), exist_ok=True)
    json.dump({"capacity": cap, "screen": res, "verdict": v},
              open(VERDICT_FILE, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(v, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

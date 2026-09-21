#!/usr/bin/env python3
"""Phase 03 P0B.1 — P32K spec-off 正式 A/B（L2 终形定案）。

gates-phase03 l2_finalization.spec_off_ab：
  臂：SPECON = composite_L2/B0 配方（spec=1 DFlash2 k7）；SPECOFF = TONLY（同配方 spec=0）
  形制：W0 弃置 boot + 3 轮 × 2 臂 back-to-back 交替（认证形制 v2；每 boot 独立 cache 全冷编译）
  cells：P32K-NS-C1 ×3（主轴 decode/aggregate/TPOT/冷 TTFT）
        + P32K-WARM-C1 ×1（暖 TTFT 轴，warm_prefix 重放）
        + D565-F512-C1 ×1（控制轴）
  判定（另行 eval 脚本）：spec-off 主轴 sign-aware ≥3% ∧ 其他轴退步 ≤5% ∧ quality 过
    → composite_L2 修订（spec off），后续 Phase 03 短档对照统一用新终形。
Screen 信号（Phase 02 §3：TONLY decode +21-30%、暖 TTFT +33%）仅资格线索，判定以本认证为准。
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
sys.path.insert(0, HERE)
import p02_screen  # noqa: E402
from p02_screen import boot_cmd, parse_capacity, stop  # noqa: E402

STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19702
REPORT = os.path.join(STAGING, "PH3-P0B", "specoff-certify-report.json")

L32 = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
       "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True}
P32K_CELL = {"fixture": "p32k", "mode": "ns", "concurrency": 1,
             "max_tokens": 256, "reps": 3}
P32K_WARM_CELL = {"fixture": "p32k", "mode": "ns", "concurrency": 1,
                  "max_tokens": 256, "reps": 1, "warm_prefix": True}
D565_CELL = {"fixture": "d565", "mode": "f512", "concurrency": 1,
             "max_tokens": 512, "reps": 1}
ARMS = {"SPECON": {"spec": 1}, "SPECOFF": {"spec": 0}}


def wait_gpu(timeout_s: int = 14400) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used",
                            "--format=csv,noheader"], capture_output=True, text=True)
        used = {ln.split(",")[0].strip(): int(ln.split(",")[1].strip().rstrip(" MiB"))
                for ln in r.stdout.splitlines() if "," in ln}
        if all(used.get(u, 1 << 30) < 1000 for u in p02_screen.TP2_UUIDS.split(",")):
            return
        time.sleep(30)
    raise SystemExit("GPU 等待超时")


def one_boot(key: str, spec: int) -> dict | None:
    wait_gpu()
    b = dict(L32)
    b["spec"] = spec
    arm_wrap = {"key": key.lower(), "boot": b}
    cmd, tag = boot_cmd(arm_wrap, PORT, "B01")
    subprocess.run(["rm", "-rf", f"{SBX}/cache-p02-{key.lower()}"])
    print(f"[{key}] booting (spec={spec})", flush=True)
    r = subprocess.run(["bash", "-c", cmd], timeout=2400)
    log = os.path.join(SBX, f"log-{tag}")
    pgid = pid = None
    for f in ("server.pgid", "server.pid"):
        p = os.path.join(log, f)
        if os.path.exists(p):
            v = int(open(p).read().strip())
            if "pgid" in f:
                pgid = v
            else:
                pid = v
    if r.returncode != 0 or pgid is None:
        print(f"[{key}] BOOT FAIL", flush=True)
        stop(pgid)
        time.sleep(10)
        return None
    entry = {"boot_ready": True, "log": log, "pgid": pgid, "spec": spec,
             "capacity": parse_capacity(log), "cells": {}}
    for cell in (P32K_CELL, P32K_WARM_CELL, D565_CELL):
        c = dict(cell)
        if c["fixture"] == "p32k":
            sfx = "WARM" if c.get("warm_prefix") else "C1-L032K"
        else:
            sfx = "C1-L0565"
        c["exp_prefix"] = f"V29-T2-P0B-{key}-L36K-{sfx}"
        ck = c["fixture"] + ("_warm" if c.get("warm_prefix") else "")
        entry["cells"][ck] = p02_screen.run_cell(c, PORT, arm_wrap, tag, pgid, pid, "B01")
    entry["done"] = all(c.get("rc") == 0 for c in entry["cells"].values())
    print(f"[{key}] done={entry['done']}", flush=True)
    stop(pgid)
    time.sleep(5)   # back-to-back：boot 间不 idle
    return entry


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"warmup": None, "rounds": []}
    if doc.get("warmup") is None:
        doc["warmup"] = one_boot("WARMUP", 1) or "FAILED"   # W0：idle 后首 boot 弃置
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    for rnd in range(1, 4):
        for key, cfg in ARMS.items():
            if any(x["round"] == rnd and x["arm"] == key for x in doc["rounds"]):
                continue
            e = one_boot(f"{key}R{rnd}", cfg["spec"])
            doc["rounds"].append({"round": rnd, "arm": key, "entry": e})
            json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    print(json.dumps([{"round": x["round"], "arm": x["arm"],
                       "done": (x["entry"] or {}).get("done")}
                      for x in doc["rounds"]], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

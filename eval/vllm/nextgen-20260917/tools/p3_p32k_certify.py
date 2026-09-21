#!/usr/bin/env python3
"""P32K 修正协议认证 A/B：弃置 idle 后首 boot（平台暖 boot）+ back-to-back 交替配对。

依据 p32k-variance 实验结论：back-to-back 同形 boot 的 P32K decode spread 0.14%（7 boot），
唯一慢态 = 长时间 idle 后首个 boot（VAR-C1，57.5 vs 69.9）——慢态为平台冷启动惩罚。
协议：WARM 弃置 boot → [B0R, N3072] × 3 轮交替（每 boot 各自独立 cache，全冷编译、
无 idle 间隔），P32K-NS-C1 ×3 + D565-F512-C1 ×1（控制轴）。
判定：臂内 spread ≤3% 且轮间一致 → 认证；sign-aware vs B0R。
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
REPORT = os.path.join(STAGING, "P03-QUALIFY", "p32k-certify-report.json")

L32 = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
       "model_len": 36864, "nbt": 2048, "patch": "a"}
P32K_CELL = {"fixture": "p32k", "mode": "ns", "concurrency": 1,
             "max_tokens": 256, "reps": 3}
D565_CELL = {"fixture": "d565", "mode": "f512", "concurrency": 1,
             "max_tokens": 512, "reps": 1}
ARMS = {"B0R": {"nbt": 2048}, "N3072": {"nbt": 3072}}


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


def one_boot(key: str, nbt: int, tag_suffix: str) -> dict | None:
    wait_gpu()
    b = dict(L32)
    b["nbt"] = nbt
    b["cold"] = True
    arm_wrap = {"key": key.lower(), "boot": b}
    cmd, tag = boot_cmd(arm_wrap, PORT, "B01")
    subprocess.run(["rm", "-rf", f"{SBX}/cache-p02-{key.lower()}"])
    print(f"[{key}/{tag_suffix}] booting", flush=True)
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
    entry = {"boot_ready": True, "log": log, "pgid": pgid,
             "capacity": parse_capacity(log), "cells": {}}
    for cell in (P32K_CELL, D565_CELL):
        c = dict(cell)
        sfx = "C1-L032K" if c["fixture"] == "p32k" else "C1-L0565"
        c["exp_prefix"] = f"V29-T2-CERT-{key}-NBT{nbt}-L36K-{sfx}"
        entry["cells"][c["fixture"]] = p02_screen.run_cell(
            c, PORT, arm_wrap, tag, pgid, pid, tag_suffix)
    entry["done"] = all(c.get("rc") == 0 for c in entry["cells"].values())
    print(f"[{key}/{tag_suffix}] done={entry['done']}", flush=True)
    stop(pgid)
    time.sleep(5)   # back-to-back：boot 间不 idle
    return entry


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"warmup": None, "rounds": []}
    if doc.get("warmup") is None:
        doc["warmup"] = one_boot("WARMUP", 2048, "B01") or "FAILED"
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    for rnd in range(1, 4):
        for key, cfg in ARMS.items():
            if any(x["round"] == rnd and x["arm"] == key for x in doc["rounds"]):
                continue
            e = one_boot(f"{key}R{rnd}", cfg["nbt"], "B01")
            doc["rounds"].append({"round": rnd, "arm": key, "entry": e})
            json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    print(json.dumps([{ "round": x["round"], "arm": x["arm"],
                        "done": (x["entry"] or {}).get("done")}
                       for x in doc["rounds"]], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

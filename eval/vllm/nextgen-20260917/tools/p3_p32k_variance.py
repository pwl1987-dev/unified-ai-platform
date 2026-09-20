#!/usr/bin/env python3
"""P32K decode 跨 boot 方差表征实验（P3 发现的 boot 级双峰跟进）。

背景：P3-Qualify 中 P32K decode 出现 boot 级确定性双峰（boot 内 rep ±0.1%，
跨 boot 58.1 vs 67.6 = 16%），与编译冷/暖（B0R 映射、NBT3072Q 不映射）、
KV 容量（NBT3072Q-B03 暖容量仍慢）均不相关——需要独立表征。

协议：B0 形制（k7/nbt2048）× 8 boot，两种编译态：
  VAR-C1..VAR-C4：每 boot 独立全新 VLLM_CACHE_ROOT（全冷）
  VAR-W1..VAR-W4：共享一个 cache（W1 冷，W2-4 暖）
每 boot 只跑 P32K-NS-C1 ×3（rep 内紧致已证）+ D565-F512-C1 ×1（对照轴，
检测双峰是否 P32K 特异）。全部 boot 同窗口顺序执行。
产出：per-boot decode/capacity/init_time/compile_state → 双峰分布证据。
"""
from __future__ import annotations

import json
import os
import re
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
REPORT = os.path.join(STAGING, "P03-QUALIFY", "p32k-variance-report.json")
L32 = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
       "model_len": 36864, "nbt": 2048, "patch": "a"}

P32K_CELL = {"exp_prefix": "V29-T2-VAR-B0-L36K-C1-L032K", "fixture": "p32k",
             "mode": "ns", "concurrency": 1, "max_tokens": 256, "reps": 3}
D565_CELL = {"exp_prefix": "V29-T2-VAR-B0-L36K-C1-L0565", "fixture": "d565",
             "mode": "f512", "concurrency": 1, "max_tokens": 512, "reps": 1}


def wait_gpu(timeout_s: int = 14400) -> None:
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used",
                            "--format=csv,noheader"], capture_output=True, text=True)
        used = {ln.split(",")[0].strip(): int(ln.split(",")[1].strip().rstrip(" MiB"))
                for ln in r.stdout.splitlines() if "," in ln}
        if all(used.get(u, 1 << 30) < 1000 for u in p02_screen.TP2_UUIDS.split(",")):
            return
        time.sleep(60)
    raise SystemExit("GPU 等待超时")


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"boots": {}}
    plan = ([(f"VAR-C{i}", True) for i in range(1, 5)] +
            [(f"VAR-W{i}", False) for i in range(1, 5)])
    for key, fresh_cache in plan:
        if doc["boots"].get(key, {}).get("done"):
            continue
        wait_gpu()
        b = dict(L32)
        if fresh_cache:
            b["cold"] = True
        arm_wrap = {"key": key.lower(), "boot": b}
        # fresh_cache: 每 boot 独立 cache 目录（boot_cmd 默认 per-key，cold 只在目录不存在时清）
        cmd, tag = boot_cmd(arm_wrap, PORT, "B01")
        if fresh_cache:
            cache_dir = f"{SBX}/cache-p02-{key.lower()}"
            subprocess.run(["rm", "-rf", cache_dir])
            cmd = cmd.replace("--cold", "") + ""  # 目录已删即冷
        print(f"[{key}] booting (fresh={fresh_cache})", flush=True)
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
            print(f"[{key}] BOOT FAIL rc={r.returncode}", flush=True)
            stop(pgid)
            time.sleep(15)
            continue
        # init 时间（编译态证据）
        init_s = None
        try:
            txt = open(os.path.join(log, "server.txt"), errors="replace").read()
            m = re.search(r"init engine \(profile.*?took ([\d.]+) s", txt)
            if m:
                init_s = float(m.group(1))
        except OSError:
            pass
        entry = {"boot_ready": True, "log": log, "pid": pid, "pgid": pgid,
                 "fresh_cache": fresh_cache, "init_engine_s": init_s,
                 "capacity": parse_capacity(log), "cells": {}}
        for cell in (P32K_CELL, D565_CELL):
            c = dict(cell)
            c["exp_prefix"] = c["exp_prefix"] + f"-{key}"
            entry["cells"][c["fixture"]] = p02_screen.run_cell(
                c, PORT, arm_wrap, tag, pgid, pid, "B01")
        entry["done"] = all(c.get("rc") == 0 for c in entry["cells"].values())
        doc["boots"][key] = entry
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
        print(f"[{key}] done={entry['done']} init={init_s}s", flush=True)
        stop(pgid)
        time.sleep(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())

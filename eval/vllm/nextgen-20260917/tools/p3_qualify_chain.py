#!/usr/bin/env python3
"""P3-Qualify 链：入围方向认证形制 3-boot（VLLM_CACHE_ROOT 钉死+暖机+spread≤3% 评估）。

臂（每臂 B01-B03 共享 per-arm cache；同窗 B0 刷新对照 B0R 先行——铁律7 认证 A/B）：
  B0R     在位配方 k7/nbt2048（同窗分母，昨 12:xx 低簇不可直接比）
  NBT3072Q nbt=3072（batch1 最强信号 +17% @P32K）
  DTP2Q   draft_tp=2（C1 +3.7~4.1%）
  K5Q     spec k=5（P32K +7.6%；pos1 跨k gap 14.4pp 复核条件）
单元（镜像 B0-L32 形制 + P32K 轴）：D565-F512-C1 ×3 / D565-NS-C4 ×3 /
  P4K-C1-COLD ×3 / P4K-C1-WARM(warm_prefix) ×3 / P32K-NS-C1 ×3
接受率提取：K5Q 各 boot 服务器 metrics 快照由 p02_screen 采样链路自然落盘（sampler-metrics.jsonl），
  pos1 复核用 p02_dynk_eval.run_delta 复用。

断点续跑：report 逐臂逐 boot 落盘；GPU 忙等待；单变量纪律=每臂只差一个轴 vs B0R。
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
REPORT = os.path.join(STAGING, "P03-QUALIFY", "p3-qualify-report.json")

L32 = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
       "model_len": 36864, "patch": "a", "cold": True}

# 显式单元表（镜像 B0-L32 命名形制；staging = {prefix}-{MODE}-{boot}-R##）
CELL_SPECS = [
    {"sfx": "C1-L0565", "fixture": "d565", "mode": "f512", "concurrency": 1,
     "max_tokens": 512, "reps": 3},
    {"sfx": "C4-L0565", "fixture": "d565", "mode": "ns", "concurrency": 4,
     "max_tokens": 512, "reps": 3},
    {"sfx": "C1-P4K-COLD", "fixture": "p4k", "mode": "ns", "concurrency": 1,
     "max_tokens": 256, "reps": 3},
    {"sfx": "C1-P4K-WARM", "fixture": "p4k", "mode": "ns", "concurrency": 1,
     "max_tokens": 256, "reps": 3, "warm_prefix": True},
    {"sfx": "C1-L032K", "fixture": "p32k", "mode": "ns", "concurrency": 1,
     "max_tokens": 256, "reps": 3},
]

ARMS = [
    {"key": "B0R", "boot": {**L32, "nbt": 2048},
     "exp_root": "V29-T2-Q3-B0R-KVBF16-SD7-MS4-NBT2048-L36K"},
    {"key": "NBT3072Q", "boot": {**L32, "nbt": 3072},
     "exp_root": "V29-T2-Q3-NBT3072-KVBF16-SD7-MS4-NBT3072-L36K"},
    {"key": "DTP2Q", "boot": {**L32, "nbt": 2048, "draft_tp": 2},
     "exp_root": "V29-T2-Q3-DTP2-KVBF16-SD7-MS4-NBT2048-L36K"},
    {"key": "K5Q", "boot": {**L32, "nbt": 2048, "k": 5},
     "exp_root": "V29-T2-Q3-K5-KVBF16-SD5-MS4-NBT2048-L36K"},
]


def cells_for(arm: dict) -> list[dict]:
    out = []
    for c in CELL_SPECS:
        c = dict(c)
        c["exp_prefix"] = f"{arm['exp_root']}-{c.pop('sfx')}"
        out.append(c)
    return out


TP2_UUIDS = p02_screen.TP2_UUIDS.split(",")


def gpu_free() -> bool:
    r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used",
                        "--format=csv,noheader"], capture_output=True, text=True)
    used = {ln.split(",")[0].strip(): int(ln.split(",")[1].strip().rstrip(" MiB"))
            for ln in r.stdout.splitlines() if "," in ln}
    return all(used.get(u, 1 << 30) < 1000 for u in TP2_UUIDS)


def wait_gpu(timeout_s: int = 86400) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if gpu_free():
            # 双保险：本战役端口无人监听才抢
            r = subprocess.run(["bash", "-c", "ss -tln | grep -c ':19702 '"],
                               capture_output=True, text=True)
            if r.stdout.strip() == "0":
                return
        time.sleep(60)
    raise SystemExit("GPU3+4 等待超时")


def wait_health(timeout_s: int = 1500) -> bool:
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)
    return False


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"arms": {}}
    for arm in ARMS:
        key = arm["key"]
        if key not in doc["arms"]:
            doc["arms"][key] = {}
        for boot_tag in ("B01", "B02", "B03"):
            if doc["arms"][key].get(boot_tag, {}).get("done"):
                continue
            wait_gpu()
            arm_wrap = {"key": key, "boot": arm["boot"]}
            cmd, tag = boot_cmd(arm_wrap, PORT, boot_tag)
            print(f"[{key}/{boot_tag}] booting {tag}", flush=True)
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
            if r.returncode != 0 or pgid is None or not wait_health():
                doc["arms"][key][boot_tag] = {"done": False, "boot_ready": False,
                                              "rc": r.returncode, "log": log}
                json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
                print(f"[{key}/{boot_tag}] BOOT FAIL rc={r.returncode}", flush=True)
                stop(pgid)
                time.sleep(15)
                continue
            entry = {"boot_ready": True, "log": log, "pid": pid, "pgid": pgid,
                     "capacity": parse_capacity(log), "cells": {}}
            for cell in cells_for(arm):
                res = p02_screen.run_cell(cell, PORT, arm_wrap, tag, pgid, pid, boot_tag)
                entry["cells"][cell["exp_prefix"].split("-", 4)[-1]] = res
            entry["done"] = all(c.get("rc") == 0 for c in entry["cells"].values())
            doc["arms"][key][boot_tag] = entry
            json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
            print(f"[{key}/{boot_tag}] done={entry['done']} pgid={pgid}", flush=True)
            stop(pgid)
            time.sleep(10)
    print(json.dumps({k: {b: v.get("done") for b, v in boots.items()}
                      for k, boots in doc["arms"].items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

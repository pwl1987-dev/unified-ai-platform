#!/usr/bin/env python3
"""P1-SCR-BATCH2 链编排：match-unit / retention / admission 三向 12 boot（GPU3+4）。

臂序（便宜先行）：MU 4 boot（尾部改写单元）→ RET 4 boot（同单元 + churn/多轮）
→ ADM 3 boot（open-loop p4k+p32k）→ ADMX220 1 boot（P220K 在途=1 vs B0-X220）。
断点续跑：report 逐臂落盘；GPU 忙则等待（每 60s 复查，不抢非本战役进程）。
每 boot 后 re-verify 下一 boot 前卡位（UUID gate 继承 p02_screen）。
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
REPORT = os.path.join(STAGING, "P02-SCREEN", "p1-batch2-report.json")

L32_BOOT = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
            "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True}

ARMS = [
    # ---- match-unit（i 向）：同单元集跨臂可比（fixture 冻结）----
    {"key": "MUDEF", "direction": "match_unit", "boot": {**L32_BOOT, "match_unit": 0},
     "cells": ["tailrw"]},
    {"key": "MU32", "direction": "match_unit", "boot": {**L32_BOOT, "match_unit": 32},
     "cells": ["tailrw"]},
    {"key": "MU64", "direction": "match_unit", "boot": {**L32_BOOT, "match_unit": 64},
     "cells": ["tailrw"]},
    {"key": "MU128", "direction": "match_unit", "boot": {**L32_BOOT, "match_unit": 128},
     "cells": ["tailrw"]},
    # ---- retention（h 向）：0=仅语义 / 1024=周期 / none=密集 / DEF=UNSET 对照 ----
    {"key": "RETDEF", "direction": "retention", "boot": {**L32_BOOT},
     "cells": ["tailrw"]},
    {"key": "RET0", "direction": "retention",
     "boot": {**L32_BOOT, "retention": "0"}, "cells": ["tailrw"]},
    {"key": "RET1024", "direction": "retention",
     "boot": {**L32_BOOT, "retention": "1024"}, "cells": ["tailrw"]},
    {"key": "RETNONE", "direction": "retention",
     "boot": {**L32_BOOT, "retention": "none"}, "cells": ["tailrw"]},
    # ---- admission（g 向）：在途阀 q8/q32 vs 无阀对照 ----
    {"key": "ADMCTL", "direction": "admission", "boot": {**L32_BOOT},
     "cells": ["openloop_p4k", "openloop_p32k"]},
    {"key": "ADMQ8", "direction": "admission",
     "boot": {**L32_BOOT, "queued_reqs": 8}, "cells": ["openloop_p4k", "openloop_p32k"]},
    {"key": "ADMQ32", "direction": "admission",
     "boot": {**L32_BOOT, "queued_reqs": 32}, "cells": ["openloop_p4k", "openloop_p32k"]},
    # ---- x220 在途=1（admission 子判据）vs B0-X220 ----
    {"key": "ADMX220", "direction": "admission",
     "boot": {"tp": 2, "ms": 1, "spec": 1, "kv_dtype": "bfloat16",
              "model_len": 225280, "nbt": 2048, "patch": "a", "cold": True,
              "queued_reqs": 1},
     "cells": ["p220k_c1", "verbatim"]},
]

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
            return
        time.sleep(60)
    raise SystemExit("GPU3+4 等待超时")


def wait_health(port: int, timeout_s: int = 1500) -> bool:
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)
    return False


def run_tailrw(arm: dict, tag: str, pgid: int, pid: int) -> dict:
    r = subprocess.run([sys.executable, os.path.join(HERE, "p1_batch2_tailrw.py"),
                        "--port", str(PORT), "--arm-key", arm["key"],
                        "--reps", "3", "--churn", "40",
                        "--server-pid", str(pid), "--tag", tag],
                       timeout=3600, capture_output=True, text=True)
    return {"rc": r.returncode, "tail": r.stdout[-2000:] + r.stderr[-500:]}


def run_openloop(arm: dict, fixture: str, tag: str, pid: int) -> dict:
    r = subprocess.run([sys.executable, os.path.join(HERE, "p1_batch2_openloop.py"),
                        "--port", str(PORT), "--arm-key", arm["key"],
                        "--fixture", fixture, "--server-pid", str(pid)],
                       timeout=7200, capture_output=True, text=True)
    return {"rc": r.returncode, "tail": r.stdout[-3000:] + r.stderr[-500:]}


def run_p220k(arm: dict, tag: str, pgid: int, pid: int) -> dict:
    """P220K C1 ns ×3 —— 复用 p02_screen.run_cell，与 B0-X220 完全同形制。"""
    cell = {"exp_prefix": "V29-T2-SCR-ADM220-Q1-MS1-NBT2048-X220-C1-L220K",
            "fixture": "p220k", "mode": "ns", "concurrency": 1,
            "max_tokens": 128, "reps": 3}
    arm_wrap = {"key": arm["key"], "boot": arm["boot"]}
    return p02_screen.run_cell(cell, PORT, arm_wrap, tag, pgid, pid, "B01")


def run_verbatim(arm: dict, tag: str) -> dict:
    out = os.path.join(STAGING, f"{arm['key']}-B01-VERBATIM")
    r = subprocess.run([sys.executable, os.path.join(HERE, "verbatim_check.py"),
                        "probe", "--api", f"http://127.0.0.1:{PORT}/v1",
                        "--out", out, "--experiment-id", f"{arm['key']}-B01-VERBATIM"],
                       timeout=1800, capture_output=True, text=True)
    verdict = None
    vp = os.path.join(out, "verbatim-result.json")
    if os.path.exists(vp):
        verdict = json.load(open(vp)).get("PASS")
    return {"rc": r.returncode, "PASS": verdict}


def nondefault_flags(log_dir: str, arm: dict) -> dict:
    """从 server.txt 的 non-default args 行取证生效旗标（retention/queued/match-unit）。"""
    out = {}
    try:
        text = open(os.path.join(log_dir, "server.txt"), errors="replace").read()
    except OSError:
        return out
    m = re.search(r"non-default args: (.+)", text)
    if m:
        args = m.group(1)
        for key in ("max_num_queued_reqs", "prefix_cache_retention_interval",
                    "prefix_match_unit"):
            mm = re.search(rf"'{key}': ([^,}}]+)", args)
            if mm:
                out[key] = mm.group(1).strip().rstrip(",")
    return out


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"arms": {}}
    for arm in ARMS:
        key = arm["key"]
        if doc["arms"].get(key, {}).get("done"):
            continue
        wait_gpu()
        b = dict(arm["boot"])
        arm_wrap = {"key": key, "boot": b}
        cmd, tag = boot_cmd(arm_wrap, PORT, "B01")
        print(f"[{key}] booting: {tag}", flush=True)
        r = subprocess.run(["bash", "-c", cmd], timeout=2400)
        log = os.path.join(SBX, f"log-{tag}")
        pgid = pid = None
        for f in ("server.pgid", "server.pid"):
            p = os.path.join(log, f)
            if os.path.exists(p):
                try:
                    v = int(open(p).read().strip())
                    if "pgid" in f:
                        pgid = v
                    else:
                        pid = v
                except ValueError:
                    pass
        if r.returncode != 0 or pgid is None or not wait_health(PORT):
            doc["arms"][key] = {"done": False, "boot_ready": False,
                                "rc": r.returncode, "log": log}
            json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
            print(f"[{key}] BOOT FAIL rc={r.returncode}", flush=True)
            stop(pgid)
            time.sleep(15)
            continue
        entry: dict = {"boot_ready": True, "log": log, "pid": pid, "pgid": pgid,
                       "capacity": parse_capacity(log),
                       "flags_effective": nondefault_flags(log, arm), "cells": {}}
        for cell in arm["cells"]:
            if cell == "tailrw":
                entry["cells"]["tailrw"] = run_tailrw(arm, tag, pgid, pid)
            elif cell.startswith("openloop_"):
                fx = cell.split("_", 1)[1]
                entry["cells"][cell] = run_openloop(arm, fx, tag, pid)
            elif cell == "p220k_c1":
                entry["cells"]["p220k_c1"] = run_p220k(arm, tag, pgid, pid)
            elif cell == "verbatim":
                entry["cells"]["verbatim"] = run_verbatim(arm, tag)
        entry["done"] = all(c.get("rc") == 0 for c in entry["cells"].values())
        doc["arms"][key] = entry
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
        print(f"[{key}] done={entry['done']} stopped pgid={pgid}", flush=True)
        stop(pgid)
        time.sleep(10)
    print(json.dumps({k: v.get("done") for k, v in doc["arms"].items()},
                     ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

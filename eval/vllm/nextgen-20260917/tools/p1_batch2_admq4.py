#!/usr/bin/env python3
"""P1-SCR-BATCH2 补臂：ADMQ4 —— 紧阀（在途=MS=4，零排队、超额即 503）。

动机：ADMQ8（在途≤8）在 Screen 负载下不 binding（0 拒绝、waiting_max=3<<8），
p95 差异为噪声——阀从未激活，策略面未被测到。q4=MS 时任何排队即超额，
是 admission 机制的最锐利探针（gates: overload p95 保护 + 503 单调可重试）。

用法: p1_batch2_admq4.py   （GPU3+4 空闲时自行 boot/测/停，写入 batch2 report）
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
REPORT = os.path.join(STAGING, "P02-SCREEN", "p1-batch2-report.json")
ARM = {"key": "ADMQ4", "direction": "admission",
       "boot": {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
                "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True,
                "queued_reqs": 4},
       "cells": ["openloop_p4k", "openloop_p32k"]}


def main() -> int:
    doc = json.load(open(REPORT))
    if doc["arms"].get("ADMQ4", {}).get("done"):
        print("ADMQ4 already done")
        return 0
    arm_wrap = {"key": ARM["key"], "boot": ARM["boot"]}
    cmd, tag = boot_cmd(arm_wrap, PORT, "B01")
    print(f"[ADMQ4] booting {tag}", flush=True)
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
    import urllib.request

    def healthy() -> bool:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/health", timeout=3) as h:
                return h.status == 200
        except Exception:  # noqa: BLE001
            return False

    t0 = time.time()
    while time.time() - t0 < 1500 and not healthy():
        time.sleep(5)
    if r.returncode != 0 or pgid is None or not healthy():
        print(f"[ADMQ4] BOOT FAIL rc={r.returncode}", flush=True)
        stop(pgid)
        return 1
    entry = {"boot_ready": True, "log": log, "pid": pid, "pgid": pgid,
             "capacity": parse_capacity(log), "cells": {}}
    for fx in ("p4k", "p32k"):
        rr = subprocess.run([sys.executable, os.path.join(HERE, "p1_batch2_openloop.py"),
                             "--port", str(PORT), "--arm-key", "ADMQ4",
                             "--fixture", fx, "--server-pid", str(pid)],
                            timeout=7200)
        entry["cells"][f"openloop_{fx}"] = {"rc": rr.returncode}
    entry["done"] = all(c.get("rc") == 0 for c in entry["cells"].values())
    doc["arms"]["ADMQ4"] = entry
    json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    print(f"[ADMQ4] done={entry['done']} pgid={pgid}", flush=True)
    stop(pgid)
    return 0


if __name__ == "__main__":
    sys.exit(main())

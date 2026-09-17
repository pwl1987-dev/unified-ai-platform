#!/usr/bin/env python3
"""P2 Layer A TP2 最小资格臂（GPU3+4/19702）——0.28 参照 vs 0.29 Layer A。

MASTER §7.1：TP2 最小资格 = D565 F512 ×3 + P4K + quality smoke + MRV2 proof。
断点续跑同 p2_layer_a。Screen 级（1 boot/臂；TP1 已 Qualify，TP2 只需资格面）。
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
STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19702
TP2_UUIDS = "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e"
OUT_FILE = os.path.join(STAGING, "P2-LAYERA", "layer-a-tp2-report.json")

ARMS = [
    {"key": "LA28REF-TP2", "boot": "028", "prefix": "V28-T2-Q0-KVAUTO-SD0-MS1-NBT2048-C1-L032K-LA28REF",
     "cache": f"{SBX}/cache-la28ref"},
    {"key": "LA29A-TP2", "boot": "029", "prefix": "V29-T2-Q0-KVAUTO-SD0-MS1-NBT2048-C1-L032K-LA29A",
     "cache": f"{SBX}/cache-la29a"},
]


def boot(arm: dict) -> tuple[bool, int | None, str]:
    if arm["boot"] == "028":
        script = "p1_boot028.sh"
    else:
        script = "boot029_nextgen.sh"
    tag = f"la2-{arm['key'].lower()}"
    cmd = (f"cd {HERE} && VLLM_CACHE_ROOT={arm['cache']} setsid bash {script} "
           f"{tag} {PORT} 2 1 --kv-dtype auto --model-len 32768 --spec 0"
           + ("" if arm["boot"] == "028" else " --patch a")
           + f" > {SBX}/boot-{tag}.log 2>&1")
    r = subprocess.run(["bash", "-c", cmd], timeout=1800)
    log = os.path.join(SBX, f"log-{tag}")
    pgid = None
    pg = os.path.join(log, "server.pgid")
    if os.path.exists(pg):
        try:
            pgid = int(open(pg).read().strip())
        except Exception:  # noqa: BLE001
            pgid = None
    return r.returncode == 0, pgid, log


def stop(pgid: int | None) -> None:
    if pgid is None or pgid == os.getpgid(0):
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


def run_arm_tool(arm: dict, fixture: str, runs: str, max_tokens: int, pgid: int, pid: int) -> int:
    cmd = [sys.executable, os.path.join(HERE, "run_arm.py"),
           "--api", f"http://127.0.0.1:{PORT}/v1", "--port", str(PORT),
           "--tp", "2", "--ms", "1", "--gpu-uuids", TP2_UUIDS,
           "--server-pid", str(pid), "--server-pgid", str(pgid),
           "--tag", f"la2-{arm['key'].lower()}",
           "--exp-prefix", arm["prefix"] if fixture == "d565" else arm["prefix"] + "-P4K",
           "--runs", *runs.split(), "--fixture", fixture, "--max-tokens", str(max_tokens)]
    return subprocess.run(cmd, timeout=max_tokens * 60 + 2400).returncode


def verbatim_probe(arm: dict) -> int:
    out = os.path.join(STAGING, f"{arm['prefix']}-TP2-VERBATIM")
    return subprocess.run([sys.executable, os.path.join(HERE, "verbatim_check.py"),
                           "probe", "--api", f"http://127.0.0.1:{PORT}/v1",
                           "--out", out, "--experiment-id",
                           f"{arm['prefix']}-TP2-VERBATIM"], timeout=1800).returncode


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    for arm in ARMS:
        if doc.get(arm["key"], {}).get("done"):
            continue
        ready, pgid, log = boot(arm)
        if not ready:
            doc[arm["key"]] = {"done": False, "boot_ready": False, "log": log}
            json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
            print(f"[{arm['key']}] BOOT FAIL", flush=True)
            continue
        pid = int(open(os.path.join(log, "server.pid")).read().strip())
        rc1 = run_arm_tool(arm, "d565", "ns:1 f512:3", 512, pgid, pid)
        rc2 = run_arm_tool(arm, "p4k", "ns:3", 256, pgid, pid)
        rc3 = verbatim_probe(arm)
        mrv2 = "Using V2 Model Runner" in open(os.path.join(log, "server.txt"), errors="replace").read()
        doc[arm["key"]] = {"done": rc1 == rc2 == rc3 == 0, "boot_ready": True, "log": log,
                           "rc": {"d565": rc1, "p4k": rc2, "verbatim": rc3},
                           "mrv2_proven": mrv2 if arm["boot"] == "029" else None}
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
        stop(pgid)
        time.sleep(10)
    print(json.dumps({k: {"done": v.get("done"), "mrv2": v.get("mrv2_proven")}
                      for k, v in doc.items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

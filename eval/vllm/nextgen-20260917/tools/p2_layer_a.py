#!/usr/bin/env python3
"""P2 Layer A TP1 — 0.28 同形制参照 vs 0.29 Layer A（GPU2/19701，计划 v1.2）。

臂（同为 target-only + W4A16 + native KV(auto) + 32K + MS1 + NBT2048）：
  LA28REF: vllm28-env + overlay（embed-quant 补丁所在）+ kv auto + spec 0
  LA29A  : vllm29-env（unit-a 已移植）+ kv auto + spec 0 + patch a 校验
每臂：boot → run_arm(d565 ns:1 f512:3) + P4K natural-stop + verbatim probe → MRV2 证据抓取 → stop。
Gate（gates-phase01.layer_a）：D565 F512 回退 ≤5%（vs 同形制 0.28 臂）；spread ≤3%；质量核心轴一致。
断点续跑：按 exp 目录存在判据跳过。
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
STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19701
TP1_UUID = "GPU-41a1986d-e745-9e40-c520-09490081fd44"
OUT_FILE = os.path.join(STAGING, "P2-LAYERA", "layer-a-tp1-report.json")

ARMS = [
    {"key": "LA28REF", "boot": "028", "prefix": "V28-T1-Q0-KVAUTO-SD0-MS1-NBT2048-C1-L032K-LA28REF",
     "cache": f"{SBX}/cache-la28ref"},
    {"key": "LA29A", "boot": "029", "prefix": "V29-T1-Q0-KVAUTO-SD0-MS1-NBT2048-C1-L032K-LA29A",
     "cache": f"{SBX}/cache-la29a"},
]


def boot(arm: dict, bno_hint: str) -> tuple[bool, int | None, str]:
    if arm["boot"] == "028":
        script, extra = "p1_boot028.sh", ""
    else:
        script, extra = "--patch a", ""
        script = "boot029_nextgen.sh"
    cmd = (f"cd {HERE} && VLLM_CACHE_ROOT={arm['cache']} setsid bash {script} "
           f"la-{arm['key'].lower()}-{bno_hint} {PORT} 1 1 "
           f"--kv-dtype auto --model-len 32768 --spec 0 {extra}"
           f" > {SBX}/boot-la-{arm['key'].lower()}-{bno_hint}.log 2>&1")
    r = subprocess.run(["bash", "-c", cmd], timeout=1800)
    log = os.path.join(SBX, f"log-la-{arm['key'].lower()}-{bno_hint}")
    pgid = None
    pg = os.path.join(log, "server.pgid")
    if os.path.exists(pg):
        try:
            pgid = int(open(pg).read().strip())
        except Exception:  # noqa: BLE001
            pgid = None
    return r.returncode == 0, pgid, log


def stop(pgid: int | None) -> None:
    if pgid is None:
        return
    if pgid == os.getpgid(0):
        print(f"[stop] REFUSE own pgid {pgid}", flush=True)
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
           "--tp", "1", "--ms", "1", "--gpu-uuids", TP1_UUID,
           "--server-pid", str(pid), "--server-pgid", str(pgid),
           "--tag", f"la-{arm['key'].lower()}",
           "--exp-prefix", arm["prefix"] if fixture == "d565" else arm["prefix"] + "-P4K",
           "--runs", *runs.split(), "--fixture", fixture, "--max-tokens", str(max_tokens)]
    return subprocess.run(cmd, timeout=max_tokens * 60 + 2400).returncode


def verbatim_probe(arm: dict, out_key: str) -> int:
    out = os.path.join(STAGING, f"{arm['prefix']}-{out_key}-VERBATIM")
    return subprocess.run([sys.executable, os.path.join(HERE, "verbatim_check.py"),
                           "probe", "--api", f"http://127.0.0.1:{PORT}/v1",
                           "--out", out, "--experiment-id",
                           f"{arm['prefix']}-{out_key}-VERBATIM"],
                          timeout=1800).returncode


def mrv2_evidence(log: str, arm_key: str) -> dict:
    ev = {"arm": arm_key, "lines": [], "mrv2_markers": []}
    srv = os.path.join(log, "server.txt")
    if not os.path.exists(srv):
        return ev
    for line in open(srv, errors="replace"):
        if re.search(r"(?i)mrv2|model runner v2|batch.?sharded|fallback", line):
            ev["lines"].append(line.strip()[:250])
            if re.search(r"(?i)mrv2", line):
                ev["mrv2_markers"].append(line.strip()[:120])
    ev["mrv2_proven"] = len(ev["mrv2_markers"]) > 0
    return ev


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    for arm in ARMS:
        if arm["key"] in doc and doc[arm["key"]].get("done"):
            print(f"[{arm['key']}] done, skip", flush=True)
            continue
        bno = str(int(time.strftime("%H%M")))
        ready, pgid, log = boot(arm, bno)
        if not ready:
            doc[arm["key"]] = {"done": False, "boot_ready": False, "log": log}
            json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
            print(f"[{arm['key']}] BOOT FAIL", flush=True)
            continue
        pid = int(open(os.path.join(log, "server.pid")).read().strip())
        rc1 = run_arm_tool(arm, "d565", "ns:1 f512:3", 512, pgid, pid)
        rc2 = run_arm_tool(arm, "p4k", "ns:3", 256, pgid, pid)
        rc3 = verbatim_probe(arm, "SMOKE")
        ev = mrv2_evidence(log, arm["key"])
        all_ok = rc1 == rc2 == rc3 == 0
        doc[arm["key"]] = {"done": all_ok, "boot_ready": True, "log": log,
                           "rc": {"d565": rc1, "p4k": rc2, "verbatim": rc3}, "mrv2": ev}
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
        stop(pgid)
        time.sleep(10)
    print(json.dumps({k: {"done": v.get("done"), "rc": v.get("rc"),
                          "mrv2_proven": (v.get("mrv2") or {}).get("mrv2_proven")}
                      for k, v in doc.items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

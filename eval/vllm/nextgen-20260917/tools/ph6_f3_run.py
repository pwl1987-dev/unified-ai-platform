#!/usr/bin/env python3
"""ph6_f3_run.py — Phase 06 F3：T2 dual champion 3-boot 资格补足 + T1 漂移对照。

形制（gates-phase06 gate_f.F3）：与 PH5-P3 dual cell 逐字同源——
  boot（ph5_boot.sh 冻结母本 + ph5_p1_run.TOPOS 拓扑表 + v1.1 router ph5_router.py）
  → verbatim canary（first backend）
  → dual_2xp32k ×3 reps + dual_2xp128kt ×3 reps（T1 对照只跑 dual_2xp32k；
    ph5_workload multi 场景，da/db 会话，与 P1/P3 cell 实参一致）
  → 每 rep 快照到 raw/staging/PH6-P3/dual-{T}-{BOOT}-R{i}/（ph5 固定目录会被
    下一次 boot 覆写，故每 rep 立即快照 cell-summary + 五件套子目录）
  → 清场（自有 PGID 核验杀）

用法：ph6_f3_run.py --plan T2-B01,T2-B02,T2-B03,T1-B04   （顺序执行）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import time

import ph5_p1_run
from ph5_p1_run import TOPOS, UUID, boot_backend, kill_own, log, sh, wait_health

HERE = os.path.dirname(os.path.abspath(__file__))
PY = "/data/tools/vllm29-env/bin/python"
SBX = "/data/sandbox/nextgen-20260917"
NG = os.path.dirname(HERE)
ROUTER_PORT = 19710
REPS = 3


def run_dual(out_dir: str, exp: str, fixture: str, mt: int, rlog: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    cmd = [PY, os.path.join(HERE, "ph5_workload.py"), "--scenario", "multi",
           "--api", f"http://127.0.0.1:{ROUTER_PORT}/v1", "--experiment-id", exp,
           "--out-dir", out_dir, "--route-log", rlog,
           "--sess", f"da:{fixture}:{mt}", "--sess", f"db:{fixture}:{mt}"]
    r = sh(cmd, timeout=3600)
    log(f"[dual] {exp} rc={r.returncode}")
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="如 T2-B01,T2-B02,T2-B03,T1-B04")
    args = ap.parse_args()
    results = {}
    for item in args.plan.split(","):
        topo, boot_tag = item.split("-")
        spec = TOPOS[topo]
        log(f"=== F3 arm {topo} {boot_tag} start ===")
        t0 = time.time()
        summary = {"topology": topo, "boot": boot_tag, "cells": {}}
        try:
            for tag, port, gpus, mlen, ms in spec["backends"]:
                boot_backend(tag, port, gpus, mlen, ms)
            if not all(wait_health(b[1], b[0]) for b in spec["backends"]):
                summary["boot"] = "FAILED"
                results[item] = summary
                continue
            # v1.1 router（与 P1/P3 逐字同形制：ph5_router + |max_len 声明）
            rargs = [PY, os.path.join(HERE, "ph5_router.py")]
            for tag, port, gpus, mlen, ms in spec["backends"]:
                rargs += ["--backend", f"{tag}=http://127.0.0.1:{port}|{mlen}"]
            rlog = f"{SBX}/ph6-f3-routes-{topo}-{boot_tag}.jsonl"
            rargs += ["--port", str(ROUTER_PORT), "--route-log", rlog]
            router = subprocess.Popen(rargs, stdout=open(f"{SBX}/ph6-router-f3-{topo}-{boot_tag}.log", "w"),
                                      stderr=subprocess.STDOUT, start_new_session=True)
            time.sleep(3)
            ok_router = router.poll() is None and sh(
                ["curl", "-sf", "--max-time", "3",
                 f"http://127.0.0.1:{ROUTER_PORT}/healthz"]).returncode == 0
            if not ok_router:
                summary["router"] = "FAILED"
                results[item] = summary
                try:
                    os.killpg(router.pid, signal.SIGTERM)
                except Exception:
                    pass
                continue
            # verbatim canary（first backend，P3 形制）
            vd = os.path.join(NG, "raw", "staging", f"PH6-P3-V-{topo}-{boot_tag}")
            os.makedirs(vd, exist_ok=True)
            ftag, fport = spec["backends"][0][0], spec["backends"][0][1]
            vr = sh([PY, os.path.join(HERE, "verbatim_check.py"), "probe",
                     "--api", f"http://127.0.0.1:{fport}/v1", "--out-dir", vd,
                     "--experiment-id", f"PH6-F3-{topo}-{boot_tag}-VERBATIM"], timeout=600)
            summary["verbatim"] = {"rc": vr.returncode}
            # dual cells ×reps（每 rep 快照）
            for rep in range(1, REPS + 1):
                for scen, fixture, mt in (("dual", "p32k", 256),
                                          ("dual128", "p128kt", 128)):
                    if scen == "dual128" and topo == "T1":
                        summary["capacity_limit"] = ["dual128(TP1@36864)"]
                        continue
                    live = os.path.join(NG, "raw", "staging", "PH6-P1", f"{scen}-{topo}")
                    exp = f"PH5-P1-{topo}-DUAL-{'P32K' if scen=='dual' else 'P128KT'}"
                    rc = run_dual(live, exp, fixture, mt, rlog)
                    snap = os.path.join(NG, "raw", "staging", "PH6-P3",
                                        f"dual{'' if scen=='dual' else '128'}-{topo}-{boot_tag}-R{rep}")
                    if os.path.exists(snap):
                        shutil.rmtree(snap)
                    shutil.copytree(live, snap)
                    summary["cells"][f"{scen}_R{rep}"] = {"rc": rc, "snap": snap}
            summary["status"] = "COMPLETE"
            try:
                os.killpg(router.pid, signal.SIGTERM)
            except Exception:
                pass
        finally:
            for tag, *_ in spec["backends"]:
                kill_own(tag)
            summary["wall_s"] = round(time.time() - t0, 1)
            results[item] = summary
            json.dump(results, open(f"{SBX}/ph6-f3-{topo}-{boot_tag}-summary.json", "w"),
                      indent=1, ensure_ascii=False)
            log(f"=== F3 arm {item} done {summary['wall_s']}s ===")
    json.dump(results, open(f"{SBX}/ph6-f3-all-arms.json", "w"), indent=1, ensure_ascii=False)
    log("ALL F3 ARMS DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

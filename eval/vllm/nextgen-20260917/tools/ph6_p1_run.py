#!/usr/bin/env python3
"""ph6_p1_run.py — Phase 06 M4 臂编排器（F1 角色化路由 A/B + F2 租户隔离/驱逐）。

流程（gates-phase06 routing_ab.same_boot_rule：A/B 同一 M4 boot 内先后执行）：
  boot M4（t3tp2@19711 GPU3+4 len131072 MS2 + t3p1a@19712 GPU2 len36864 MS4
         + t3p1b@19713 GPU6 len36864 MS4，ph5_boot.sh 冻结母本）
  → verbatim canary（first backend，P3 形制）
  → 两轮交错（r1=预热轮只留档；r2=正式对，gate_f 取 r2）：
      router BLIND（ph6_router v1.1 parity）→ mix / isolation
      router ROLE （--role-pools short=t3p1a,t3p1b;long=t3tp2;batch=t3p1a,t3p1b）
                 → mix / isolation（同 evict 时序）
    每次换策略 = 重启 router 进程（backends 不动；引擎 prefix cache 保留 →
    r2 时 A/B 两臂同等热，消除先后顺序偏差）
  → route log 快照（role r2 用于 placement audit）
  → 清场（自有 PGID 核验杀）→ arm-summary.json

证据：raw/staging/PH6-P1/{mix-blind-r1,mix-role-r1,isolation-blind-r1,isolation-role-r1,
      mix-blind-r2,mix-role-r2,isolation-blind-r2,isolation-role-r2}/ + routes-*.jsonl
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
from ph5_p1_run import UUID, boot_backend, kill_own, log, sh, wait_health

HERE = os.path.dirname(os.path.abspath(__file__))
PY = "/data/tools/vllm29-env/bin/python"
SBX = "/data/sandbox/nextgen-20260917"
NG = os.path.dirname(HERE)
ROUTER_PORT = 19710

M4_BACKENDS = [("t3tp2", 19711, [3, 4], 131072, 2),
               ("t3p1a", 19712, [2], 36864, 4),
               ("t3p1b", 19713, [6], 36864, 4)]
ROLE_POOLS = "short=t3p1a,t3p1b;long=t3tp2;batch=t3p1a,t3p1b"
ISO_DURATION_S = 150.0
ISO_EVICT_AFTER_S = 60.0


def start_router(policy: str, round_tag: str):
    rargs = [PY, os.path.join(HERE, "ph6_router.py")]
    for tag, port, gpus, mlen, ms in M4_BACKENDS:
        rargs += ["--backend", f"{tag}=http://127.0.0.1:{port}|{mlen}"]
    if policy == "role":
        rargs += ["--role-pools", ROLE_POOLS]
    rlog = f"{SBX}/ph6-routes-{policy}-{round_tag}.jsonl"
    rargs += ["--port", str(ROUTER_PORT), "--route-log", rlog]
    p = subprocess.Popen(rargs, stdout=open(f"{SBX}/ph6-router-{policy}-{round_tag}.log", "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(3)
    if p.poll() is not None:
        raise RuntimeError(f"router {policy} 启动失败 rc={p.returncode}")
    hz = sh(["curl", "-sf", "--max-time", "3", f"http://127.0.0.1:{ROUTER_PORT}/healthz"])
    if hz.returncode != 0:
        raise RuntimeError("router /healthz 不通")
    return p, rlog


def stop_router(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except Exception:
        pass
    time.sleep(2)


def scenario(scen: str, policy: str, round_tag: str, api: str) -> int:
    out = os.path.join(NG, "raw", "staging", "PH6-P1", f"{scen}-{policy}-{round_tag}")
    cmd = [PY, os.path.join(HERE, "ph6_agent_workload.py"), "--scenario", scen,
           "--policy", policy, "--api", api, "--out-dir", out]
    if scen == "isolation":
        cmd += ["--duration-s", str(ISO_DURATION_S),
                "--churn-waves", "6", "--churn-interval-s", "20",
                "--evict-after-s", str(ISO_EVICT_AFTER_S)]
    r = sh(cmd, timeout=1800)
    log(f"[scene] {scen}-{policy}-{round_tag} rc={r.returncode}")
    if r.returncode != 0:
        log(r.stdout[-800:] + r.stderr[-800:])
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-boot", action="store_true")
    args = ap.parse_args()
    arm = {"arm": "M4", "t_start": time.time(), "cells": {}}
    auth4 = ",".join(UUID[g] for g in (2, 3, 4, 6))
    sampler = subprocess.Popen(
        [PY, os.path.join(HERE, "ph5_energy_node.py"), "--window-label", "PH6-P1-M4-full",
         "--authorized-uuids", auth4, "--out", f"{SBX}/energy-ph6-m4"],
        stdout=open(f"{SBX}/energy-ph6-m4.up.log", "w"), stderr=subprocess.STDOUT,
        start_new_session=True)
    router = None
    try:
        if not args.skip_boot:
            for tag, port, gpus, mlen, ms in M4_BACKENDS:
                boot_backend(tag, port, gpus, mlen, ms)
            if not all(wait_health(b[1], b[0]) for b in M4_BACKENDS):
                arm["boot"] = "FAILED"
                return 11
        arm["t_cells_start"] = time.time()
        # verbatim canary（first backend 直轨，P3 形制）
        vd = os.path.join(NG, "raw", "staging", "PH6-P1-V-M4")
        os.makedirs(vd, exist_ok=True)
        vr = sh([PY, os.path.join(HERE, "verbatim_check.py"), "probe",
                 "--api", "http://127.0.0.1:19711/v1", "--out-dir", vd,
                 "--experiment-id", "PH6-M4-VERBATIM"], timeout=600)
        arm["verbatim"] = {"rc": vr.returncode}
        log(f"[canary] verbatim rc={vr.returncode}")
        RAPI = f"http://127.0.0.1:{ROUTER_PORT}/v1"
        for round_tag, formal in (("r1", False), ("r2", True)):
            for policy in ("blind", "role"):
                router, rlog = start_router(policy, round_tag)
                tag = f"{policy}-{round_tag}"
                arm["cells"][f"mix_{tag}"] = scenario("mix", policy, round_tag, RAPI)
                arm["cells"][f"isolation_{tag}"] = scenario("isolation", policy, round_tag, RAPI)
                if formal and policy == "role":
                    # 正式 role r2 route log → staging（placement audit 输入）
                    dst = os.path.join(NG, "raw", "staging", "PH6-P1", "routes-role.jsonl")
                    shutil.copy(rlog, dst)
                stop_router(router)
                router = None
        arm["status"] = "COMPLETE"
    finally:
        if router:
            stop_router(router)
        for tag, *_ in M4_BACKENDS:
            kill_own(tag)
        arm["t_end"] = time.time()
        try:
            os.killpg(sampler.pid, signal.SIGTERM)
        except Exception:
            pass
        json.dump(arm, open(f"{SBX}/ph6-m4-arm-summary.json", "w"), indent=1, ensure_ascii=False)
        log(f"[M4] arm DONE summary={SBX}/ph6-m4-arm-summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

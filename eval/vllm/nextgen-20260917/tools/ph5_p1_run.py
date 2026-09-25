#!/usr/bin/env python3
"""ph5_p1_run.py — Phase 05 P1 拓扑臂编排器（T1/T2/T3/T4，gates-phase05 screen_p1）。

单拓扑一臂全流程：
  boot 全 backends（ph5_boot.sh）→ router v1.1 → 整机能量采样（boot 窗先开）→
  cell 套件（direct C1 refs / router C1 / dual / four / batch / mixed / sticky / failover）→
  T4 early-stop 判定 → 清场（自有 PGID 核验杀）→ arm-summary.json

cell 实参=认证形制：D565=F512、P32K/P4K=NS mt256、P128KT=NS mt128（PH4 勘误后认证预算）、
P220K=NS mt256（仅 T4，220000+52+256≤262144）。
证据：run_arm（warmup/thermal/3 reps/五件套）+ ph5_workload（场景）→ raw/staging/。
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
PY = "/data/tools/vllm29-env/bin/python"
SBX = "/data/sandbox/nextgen-20260917"
ROUTER_PORT = 19710
UUID = {
    2: "GPU-41a1986d-e745-9e40-c520-09490081fd44",
    3: "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae",
    4: "GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e",
    6: "GPU-30776c79-cd65-60d6-4b56-69c9b6979449",
}

TOPOS = {
    "T2": dict(backends=[("t2a", 19711, [3, 4], 131072, 2), ("t2b", 19712, [2, 6], 131072, 2)]),
    "T1": dict(backends=[("t1a", 19711, [2], 36864, 4), ("t1b", 19712, [3], 36864, 4),
                          ("t1c", 19713, [4], 36864, 4), ("t1d", 19714, [6], 36864, 4)]),
    "T3": dict(backends=[("t3tp2", 19711, [3, 4], 131072, 2), ("t3p1a", 19712, [2], 36864, 4),
                          ("t3p1b", 19713, [6], 36864, 4)]),
    "T4": dict(backends=[("t4", 19711, [2, 3, 4, 6], 262144, 2)], early_stop=True),
}


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def boot_backend(tag, port, gpus, model_len, ms) -> dict:
    uuids = ",".join(UUID[g] for g in gpus)
    tp = len(gpus)
    cmd = ["setsid", "bash", os.path.join(HERE, "ph5_boot.sh"), f"ph5-{tag}", str(port),
           str(tp), str(ms), "--uuids", uuids, "--model-len", str(model_len), "--spec", "1"]
    r = subprocess.Popen(cmd, stdout=open(f"{SBX}/ph5-{tag}.boot.log", "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    return {"tag": tag, "port": port, "proc": r, "gpus": gpus, "model_len": model_len, "ms": ms}


def wait_health(port, tag, timeout=2100) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if sh(["curl", "-sf", "-o", "/dev/null", "--max-time", "3",
               f"http://127.0.0.1:{port}/health"]).returncode == 0:
            log(f"[{tag}] READY in {time.time()-t0:.0f}s")
            return True
        time.sleep(5)
    log(f"[{tag}] HEALTH TIMEOUT")
    return False


def kill_own(tag) -> bool:
    pidf, pgidf = f"{SBX}/log-ph5-{tag}/server.pid", f"{SBX}/log-ph5-{tag}/server.pgid"
    if not os.path.exists(pidf):
        return False
    pid, pgid = int(open(pidf).read().strip()), int(open(pgidf).read().strip())
    cmd = sh(["ps", "-o", "cmd=", "-p", str(pid)]).stdout
    if "vllm" not in cmd:
        log(f"[kill_own:{tag}] pid {pid} 非 vllm（{cmd[:40]}）——拒绝")
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    for _ in range(30):
        try:
            os.kill(pid, 0)
            time.sleep(2)
        except ProcessLookupError:
            log(f"[kill_own:{tag}] TERM 完成 pgid={pgid}")
            return True
    os.killpg(pgid, signal.SIGKILL)
    return True


def run_arm_cell(exp_prefix, api, port, tp, ms, uuids, tag, fixture, mode_key, mt, conc, reps,
                 boot_tag="B01", thermal_api=None) -> list:
    cmd = [PY, os.path.join(HERE, "run_arm.py"), "--api", api, "--port", str(port),
           "--tp", str(tp), "--ms", str(ms), "--gpu-uuids", uuids,
           "--server-pid", open(f"{SBX}/log-ph5-{tag}/server.pid").read().strip(),
           "--server-pgid", open(f"{SBX}/log-ph5-{tag}/server.pgid").read().strip(),
           "--tag", f"ph5-{tag}", "--boot-tag", boot_tag,
           "--exp-prefix", exp_prefix, "--runs", f"{mode_key}:{reps}",
           "--fixture", fixture, "--max-tokens", str(mt), "--concurrency", str(conc)] \
        + (["--thermal-api", thermal_api] if thermal_api else [])
    r = sh(cmd, timeout=mt * 40 * reps + 3600)
    log(f"[cell] {exp_prefix} rc={r.returncode}")
    return [r.returncode]


def workload_cell(scenario, out_dir, exp, extra: list) -> int:
    os.makedirs(out_dir, exist_ok=True)
    cmd = [PY, os.path.join(HERE, "ph5_workload.py"), "--scenario", scenario,
           "--api", f"http://127.0.0.1:{ROUTER_PORT}/v1", "--experiment-id", exp,
           "--out-dir", out_dir, "--route-log", RLOG] + extra
    r = sh(cmd, timeout=3600)
    log(f"[scene] {exp} rc={r.returncode}")
    return r.returncode


def median_decode(prefix_glob) -> float | None:
    import glob
    import statistics
    vals = []
    for d in glob.glob(os.path.join(NG, "raw", "staging", prefix_glob)):
        mp = os.path.join(d, "metrics.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        pr = [r for r in (m.get("per_request") or []) if r.get("ok")]
        dec = [r.get("client_observed_decode_tok_s") for r in pr if r.get("client_observed_decode_tok_s")]
        if dec:
            vals.append(statistics.median(dec))
    return statistics.median(vals) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topology", choices=list(TOPOS), required=True)
    ap.add_argument("--skip-boot", action="store_true", help="backends 已在线（复用）")
    ap.add_argument("--only", default="", help="逗号分隔 cell 名子集（补测模式，其余跳过）")
    args = ap.parse_args()
    T = args.topology
    ONLY = set(x for x in args.only.split(",") if x)
    spec = TOPOS[T]
    arm = {"topology": T, "t_boot_start": time.time(), "cells": {}, "capacity_limit": []}
    auth4 = ",".join(UUID[g] for g in (2, 3, 4, 6))
    # 整机能量采样（boot 窗起算）
    sampler = subprocess.Popen(
        [PY, os.path.join(HERE, "ph5_energy_node.py"), "--window-label", f"PH5-P1-{T}-full",
         "--authorized-uuids", auth4, "--out", f"{SBX}/energy-ph5-{T}"],
        stdout=open(f"{SBX}/energy-ph5-{T}.up.log", "w"), stderr=subprocess.STDOUT,
        start_new_session=True)
    try:
        # ---- boot ----
        boots = []
        if not args.skip_boot:
            for tag, port, gpus, mlen, ms in spec["backends"]:
                boots.append(boot_backend(tag, port, gpus, mlen, ms))
            ok = all(wait_health(b["port"], b["tag"]) for b in boots)
            if not ok:
                arm["boot"] = "FAILED"
                json.dump(arm, open(f"{SBX}/ph5-{T}-arm-summary.json", "w"), indent=1)
                return 11
        arm["t_cells_start"] = time.time()   # boot/serving 能量分账界
        # ---- router ----
        rargs = ["setsid", PY, os.path.join(HERE, "ph5_router.py")]
        for tag, port, gpus, mlen, ms in spec["backends"]:
            rargs += ["--backend", f"{tag}=http://127.0.0.1:{port}|{mlen}"]
        RLOG = f"{SBX}/ph5-router-routes-{T}.jsonl"
        rargs += ["--port", str(ROUTER_PORT), "--route-log", RLOG]
        router = subprocess.Popen(rargs, stdout=open(f"{SBX}/ph5-router-{T}.log", "w"),
                                  stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(3)
        RAPI = f"http://127.0.0.1:{ROUTER_PORT}/v1"
        first = spec["backends"][0]
        ftag, fport, fgpus, fmlen, fms = first
        fuuids = ",".join(UUID[g] for g in fgpus)
        ftp = len(fgpus)
        long_capable = fmlen >= 131072

        def cell(name, fn):
            if ONLY and name not in ONLY:
                arm["cells"][name] = {"rc": "SKIPPED_FIXUP"}
                return
            t0 = time.time()
            arm["cells"][name] = {"rc": fn(), "wall_s": round(time.time() - t0, 1)}

        # ---- direct C1 refs（first backend，同日直轨）----
        cell("dir_d565_c1", lambda: run_arm_cell(
            f"V29-PH5-{T}-DIR-C1-L0565", f"http://127.0.0.1:{fport}/v1", fport, ftp, fms,
            fuuids, ftag, "d565", "f512", 512, 1, 3))
        cell("dir_p32k_c1", lambda: run_arm_cell(
            f"V29-PH5-{T}-DIR-C1-L032K", f"http://127.0.0.1:{fport}/v1", fport, ftp, fms,
            fuuids, ftag, "p32k", "ns", 256, 1, 3))
        if long_capable:
            cell("dir_p128kt_c1", lambda: run_arm_cell(
                f"V29-PH5-{T}-DIR-C1-L128KT", f"http://127.0.0.1:{fport}/v1", fport, ftp, fms,
                fuuids, ftag, "p128kt", "ns", 128, 1, 3))
        else:
            arm["capacity_limit"].append("dir_p128kt_c1(model_len<131072)")
        if fmlen >= 262144:
            cell("dir_p220k_c1", lambda: run_arm_cell(
                f"V29-PH5-{T}-DIR-C1-L220K", f"http://127.0.0.1:{fport}/v1", fport, ftp, fms,
                fuuids, ftag, "p220k", "ns", 256, 1, 3))
        # ---- router C1（overhead 轨；thermal 探测走 first backend 的 /metrics）----
        FAPI = f"http://127.0.0.1:{fport}/v1"
        cell("rtr_d565_c1", lambda: run_arm_cell(
            f"V29-PH5R-{T}-C1-L0565", RAPI, fport, ftp, fms, fuuids, ftag, "d565", "f512", 512, 1, 3,
            thermal_api=FAPI))
        cell("rtr_p32k_c1", lambda: run_arm_cell(
            f"V29-PH5R-{T}-C1-L032K", RAPI, fport, ftp, fms, fuuids, ftag, "p32k", "ns", 256, 1, 3,
            thermal_api=FAPI))
        if long_capable:
            cell("rtr_p128kt_c1", lambda: run_arm_cell(
                f"V29-PH5R-{T}-C1-L128KT", RAPI, fport, ftp, fms, fuuids, ftag, "p128kt", "ns", 128, 1, 3,
                thermal_api=FAPI))

        # ---- T4 early-stop ----
        if spec.get("early_stop"):
            axes = {}
            for nm, pat in [("d565", f"V29-PH5-{T}-DIR-C1-L0565-F512*"),
                             ("p32k", f"V29-PH5-{T}-DIR-C1-L032K-NS*"),
                             ("p128k", f"V29-PH5-{T}-DIR-C1-L128KT*")]:
                t4v = median_decode(os.path.join("raw", "staging", pat.replace("raw/staging/", "") + "*")) \
                      if False else median_decode(pat)
                t2v = median_decode(pat.replace(f"-{T}-DIR-", "-T2-DIR-"))
                axes[nm] = {"T4": t4v, "T2": t2v,
                            "gain": round((t4v - t2v) / t2v, 4) if t4v and t2v else None}
            wins = [a for a, v in axes.items() if v["gain"] is not None and v["gain"] >= 0.03]
            arm["tp4_early_stop"] = {"axes": axes, "wins": wins,
                                     "verdict": "CONTINUE" if len(wins) >= 2 else "EARLY_STOP_OUT"}
            log(f"[T4 early-stop] {json.dumps(arm['tp4_early_stop'])}")
            if len(wins) < 2:
                arm["skipped_after_early_stop"] = True
                json.dump(arm, open(f"{SBX}/ph5-{T}-arm-summary.json", "w"), indent=1, ensure_ascii=False)
                return 0  # 由 main 外层清场
        # ---- 场景 cells（through-router）----
        ST = os.path.join(NG, "raw", "staging", "PH5-P1")
        cell("dual_2xp32k", lambda: workload_cell("multi", os.path.join(ST, f"dual-{T}"),
             f"PH5-P1-{T}-DUAL-P32K", ["--sess", "da:p32k:256", "--sess", "db:p32k:256"]))
        if long_capable:
            cell("dual_2xp128kt", lambda: workload_cell("multi", os.path.join(ST, f"dual128-{T}"),
                 f"PH5-P1-{T}-DUAL-P128KT", ["--sess", "da:p128kt:128", "--sess", "db:p128kt:128"]))
        else:
            arm["capacity_limit"].append("dual_2xp128kt")
        cell("four_4xp32k", lambda: workload_cell("multi", os.path.join(ST, f"four-{T}"),
             f"PH5-P1-{T}-FOUR-P32K",
             sum([["--sess", f"f{i}:p32k:256"] for i in range(4)], [])))
        for fx, mt in (("d565", 512), ("p4k", 256)):
            for cc in (4, 8, 16):
                mk = "f512" if fx == "d565" else "ns"
                cell(f"batch_{fx}_c{cc}", lambda fx=fx, mt=mt, cc=cc, mk=mk: run_arm_cell(
                    f"V29-PH5R-{T}-C{cc}-L0{'565' if fx=='d565' else '04K'}",
                    RAPI, fport, ftp, fms, fuuids, ftag, fx, mk, mt, cc, 3,
                    thermal_api=FAPI))
        if long_capable:
            cell("mixed", lambda: workload_cell("multi", os.path.join(ST, f"mixed-{T}"),
                 f"PH5-P1-{T}-MIXED",
                 ["--sess", "long:p128kt:128", "--sess", "s1:d565:512",
                  "--sess", "s2:d565:512", "--sess", "s3:d565:512"]))
        else:
            arm["capacity_limit"].append("mixed(long 组件不可服务)")
        cell("sticky", lambda: workload_cell("sticky", os.path.join(ST, f"sticky-{T}"),
             f"PH5-P1-{T}-STICKY", ["--turns", "4", "--sticky-sessions", "2", "--parallel-new", "3"]))
        if len(spec["backends"]) > 1:
            last = spec["backends"][-1]
            kpid = int(open(f"{SBX}/log-ph5-{last[0]}/server.pid").read().strip())
            cell("failover", lambda: workload_cell("failover", os.path.join(ST, f"failover-{T}"),
                 f"PH5-P1-{T}-FAILOVER", ["--kill-pid", str(kpid), "--kill-after-s", "3", "--max-runs", "10"]))
        else:
            arm["capacity_limit"].append("failover(单 backend N/A)")
        arm["status"] = "COMPLETE"
    finally:
        # ---- 清场（自有核验杀）----
        for tag, *_ in spec["backends"]:
            kill_own(tag)
        try:
            os.killpg(router.pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep  # noqa: B018 — 占位防误引
        arm["t_end"] = time.time()
        try:
            os.killpg(sampler.pid, signal.SIGTERM)
        except Exception:
            pass
        json.dump(arm, open(f"{SBX}/ph5-{T}-arm-summary.json", "w"), indent=1, ensure_ascii=False)
        log(f"[{T}] arm DONE summary={SBX}/ph5-{T}-arm-summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

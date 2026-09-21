#!/usr/bin/env python3
"""P4-SLO 链：L2/X2 双曲线（SLO_UNDECIDED 义务）+ ceiling 晋级链（seed99 only）。

L2（B0 配方 L36K 形）：D565 closed C1/C2/C4/C8×3 + open-loop（0.25/0.5/0.75/0.9/1.1，
  冻结参数 120/300/60/900）；P32K closed C1/C2/C4×3（C8=264K<287.9K 容量可行，含容量核查）
  + open-loop（120/420/40/1500）。
X2（X128 形）：closed C1/C2×3（C4=526K>374K → CAPACITY_LIMIT 端点记录）
  + open-loop（240/900/12/3600）。
ceiling：X245K boot → needle seed99 → PASS 才进 X262K seed99（CEILING_OBSERVATION only）。
协议：WARMUP 弃置 boot（平台态）→ 全部 back-to-back；断点续跑。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
sys.path.insert(0, HERE)
import p02_screen  # noqa: E402
from p02_screen import boot_cmd, parse_capacity, stop  # noqa: E402
import p1_batch2_openloop as ol  # noqa: E402
from gen_fixtures import make_prompt  # noqa: E402

STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19702
REPORT = os.path.join(STAGING, "P04-SLO", "p4-slo-report.json")
TP2 = p02_screen.TP2_UUIDS

L36 = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
       "model_len": 36864, "nbt": 2048, "patch": "a"}
X128 = {"tp": 2, "ms": 2, "spec": 1, "kv_dtype": "bfloat16",
        "model_len": 135168, "nbt": 2048, "patch": "a"}

SLO_PARAMS = {
    "d565": {"prompt_tokens": 565, "max_tokens": 256, "warmup_s": 120, "measure_s": 300,
             "min_completed": 60, "max_test_s": 900},
    "p32k": {"prompt_tokens": 32768, "max_tokens": 256, "warmup_s": 120, "measure_s": 420,
             "min_completed": 40, "max_test_s": 1500},
    "p128k": {"prompt_tokens": 131072, "max_tokens": 128, "warmup_s": 240, "measure_s": 900,
              "min_completed": 12, "max_test_s": 3600},
}
RATIOS = (0.25, 0.50, 0.75, 0.90, 1.10)


def wait_gpu(timeout_s: int = 14400) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used",
                            "--format=csv,noheader"], capture_output=True, text=True)
        used = {ln.split(",")[0].strip(): int(ln.split(",")[1].strip().rstrip(" MiB"))
                for ln in r.stdout.splitlines() if "," in ln}
        if all(used.get(u, 1 << 30) < 1000 for u in TP2.split(",")):
            return
        time.sleep(30)
    raise SystemExit("GPU 等待超时")


def run_boot(key: str, boot_cfg: dict, tag_suffix: str) -> tuple[dict | None, int | None, int | None]:
    wait_gpu()
    subprocess.run(["rm", "-rf", f"{SBX}/cache-p02-{key.lower()}"])
    arm_wrap = {"key": key, "boot": {**boot_cfg, "cold": True}}
    cmd, tag = boot_cmd(arm_wrap, PORT, tag_suffix)
    print(f"[{key}] booting", flush=True)
    r = subprocess.run(["bash", "-c", cmd], timeout=3000)
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
        time.sleep(10)
        return None, None, None
    return {"log": log, "capacity": parse_capacity(log)}, pid, pgid


def closed_cells(key: str, boot: dict, pid: int, pgid: int, tag: str,
                 cells: list[dict]) -> list[dict]:
    out = []
    for c in cells:
        arm_wrap = {"key": key, "boot": boot}
        out.append(p02_screen.run_cell(c, PORT, arm_wrap, tag, pgid, pid, "B01"))
    return out


def openloop_curves(key: str, fixture: str, pid: int, tag: str) -> dict:
    prm = dict(SLO_PARAMS[fixture])
    ptext = make_prompt(prm["prompt_tokens"])
    api = f"http://127.0.0.1:{PORT}/v1"
    base = api.rsplit("/v1", 1)[0]
    poller = ol.MetricsPoller(base)
    poller.start()
    cl = {}
    for conc in (1, 2, 4, 8):
        cl[str(conc)] = ol.closed_loop(api, ptext, prm["max_tokens"], conc, 2,
                                       f"slo-{key}", max(120, prm["max_test_s"] // 3))
    sat = ol.saturation_est(cl, prm["max_tokens"])
    poller.waiting_max = poller.running_max = 0.0
    points = []
    for ratio in RATIOS:
        poller.preempt_first = poller.preempt_last = None
        pt = ol.open_point(api, ptext, prm["max_tokens"], sat * ratio, prm,
                           f"{key}-{fixture}-r{ratio}", poller)
        points.append(pt)
        print(json.dumps({k: pt[k] for k in ("arrival_rate", "served_ok", "ttft_p95")}),
              flush=True)
    poller.stop_flag = True
    return {"closed": cl, "sat_est": round(sat, 4), "open": points}


def needle(api: str, tokens: int, seed: int, exp: str) -> dict:
    out = os.path.join(STAGING, exp)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "needle_probe_nextgen.py"),
                        "--api", api, "--prompt-tokens", str(tokens), "--seed", str(seed),
                        "--experiment-id", exp, "--out-dir", out,
                        "--max-tokens", "64", "--gpu-uuids", TP2],
                       timeout=1800)
    res = json.load(open(os.path.join(out, "needle-result.json"))) \
        if os.path.exists(os.path.join(out, "needle-result.json")) else {}
    return {"rc": r.returncode, "PASS": res.get("PASS"), "needles_hit": res.get("needles_hit"),
            "ttft_s": res.get("ttft_s")}


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"stages": {}}
    st = doc["stages"]

    def save() -> None:
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)

    # S1 WARMUP 弃置（平台态；上一链已热则其数据亦快态，仅记录）
    if "warmup" not in st:
        info, pid, pgid = run_boot("SLOWARM", L36, "B01")
        st["warmup"] = {"info": info, "skipped": info is None}
        save()
        if pgid:
            stop(pgid)
        time.sleep(5)

    # S2 L2 D565 曲线（closed C1-C8 ×3 + open 5 点）
    if "l2_d565" not in st:
        info, pid, pgid = run_boot("SL2D565", L36, "B01")
        if info:
            cells = closed_cells("SL2D565", L36, pid, pgid, "p02-sl2d565-b01", [
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C1-L0565", "fixture": "d565",
                 "mode": "ns", "concurrency": 1, "max_tokens": 256, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C2-L0565", "fixture": "d565",
                 "mode": "ns", "concurrency": 2, "max_tokens": 256, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C4-L0565", "fixture": "d565",
                 "mode": "ns", "concurrency": 4, "max_tokens": 256, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C8-L0565", "fixture": "d565",
                 "mode": "ns", "concurrency": 8, "max_tokens": 256, "reps": 3},
            ])
            curves = openloop_curves("SL2D565", "d565", pid, "sl2d565")
            st["l2_d565"] = {"info": info, "cells": cells, "curves": curves}
            save()
            stop(pgid)
        time.sleep(5)

    # S3 L2 P32K 曲线（C1/C2/C4；C8 容量预检 8×33.04K=264.4K<287.9K → 跑，若 preempt 现象记录）
    if "l2_p32k" not in st:
        info, pid, pgid = run_boot("SL2P32K", L36, "B01")
        if info:
            cells = closed_cells("SL2P32K", L36, pid, pgid, "p02-sl2p32k-b01", [
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C1-L032K", "fixture": "p32k",
                 "mode": "ns", "concurrency": 1, "max_tokens": 256, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C2-L032K", "fixture": "p32k",
                 "mode": "ns", "concurrency": 2, "max_tokens": 256, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C4-L032K", "fixture": "p32k",
                 "mode": "ns", "concurrency": 4, "max_tokens": 256, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-L2-NBT2048-L36K-C8-L032K", "fixture": "p32k",
                 "mode": "ns", "concurrency": 8, "max_tokens": 256, "reps": 3},
            ])
            curves = openloop_curves("SL2P32K", "p32k", pid, "sl2p32k")
            st["l2_p32k"] = {"info": info, "cells": cells, "curves": curves}
            save()
            stop(pgid)
        time.sleep(5)

    # S4 X2 P128K 曲线（C1/C2 closed；C4/C8 = CAPACITY_LIMIT 端点；open 240/900/12/3600）
    if "x2_p128k" not in st:
        info, pid, pgid = run_boot("SX2P128", X128, "B01")
        if info:
            cells = closed_cells("SX2P128", X128, pid, pgid, "p02-sx2p128-b01", [
                {"exp_prefix": "V29-T2-SLO-X2-NBT2048-X128-C1-L128K", "fixture": "p128k",
                 "mode": "ns", "concurrency": 1, "max_tokens": 128, "reps": 3},
                {"exp_prefix": "V29-T2-SLO-X2-NBT2048-X128-C2-L128K", "fixture": "p128k",
                 "mode": "ns", "concurrency": 2, "max_tokens": 128, "reps": 3},
            ])
            cap = info["capacity"].get("kv_tokens")
            capacity_note = {"c4_workpoint_tokens": 4 * 131500, "kv_tokens": cap,
                             "verdict": "CAPACITY_LIMIT" if cap and 4 * 131500 > cap else "OK"}
            curves = openloop_curves("SX2P128", "p128k", pid, "sx2p128")
            st["x2_p128k"] = {"info": info, "cells": cells, "curves": curves,
                              "capacity_note": capacity_note}
            save()
            stop(pgid)
        time.sleep(5)

    # S5 ceiling 晋级链（只用 seed99）：X245K PASS → X262K；CEILING_OBSERVATION only
    # 262K 档 max_model_len=262144 = 模型 max_position_embeddings 硬上限；
    # needle 靶值 262000→261888：fixture 装配实测超靶 +133~153 tok（262153+64 > 262144
    # → HTTP 400），261888 装配后 262021+tmpl10+64=262095 ≤ 262144（headroom 49）
    for ctx, ml, pt in ((245000, 251392, 245000), (262000, 262144, 261888)):
        k = f"ceiling_{ctx//1000}k"
        if k in st and st[k].get("needle", {}).get("PASS") is None and \
                st[k].get("needle", {}).get("rc") != 0:
            del st[k]  # 无效观测（rc!=0 且 PASS=null）重跑
            save()
        if k in st:
            continue
        k = f"ceiling_{ctx//1000}k"
        if k in st:
            continue
        prev = f"ceiling_{(ctx - 17000)//1000}k"
        if ctx == 262000 and not (st.get(prev, {}).get("needle", {}).get("PASS")):
            st[k] = {"verdict": "NOT_RUN_UPSTREAM_CAPACITY" if prev not in st else
                     "NOT_RUN_UPSTREAM_FAIL"}
            save()
            continue
        boot_cfg = {"tp": 2, "ms": 1, "spec": 1, "kv_dtype": "bfloat16",
                    "model_len": ml, "nbt": 2048, "patch": "a"}
        info, pid, pgid = run_boot(f"SCEIL{ctx//1000}K", boot_cfg, "B01")
        if info:
            api = f"http://127.0.0.1:{PORT}/v1"
            nd = needle(api, pt, 99, f"SCEIL{ctx//1000}K-B01-ND{pt}-S99")
            st[k] = {"info": info, "needle": nd, "prompt_target": pt,
                     "model_len": ml,
                     "observation_class": "CEILING_OBSERVATION"}
            save()
            stop(pgid)
        time.sleep(5)
    print(json.dumps({k: ("done" if isinstance(v, dict) and (
        v.get("curves") or v.get("needle") or v.get("verdict")) else "pending")
        for k, v in st.items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

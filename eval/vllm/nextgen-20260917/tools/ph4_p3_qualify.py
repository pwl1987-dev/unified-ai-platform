#!/usr/bin/env python3
"""Phase 04 P3 — Pareto shortlist Qualify（3-boot × 4 server + holdout 首开）。

shortlist（P2 六轴 epsilon 判定）：Q0（交互/全档）、Q1M（128K 长上下文）、Q4C（C4 吞吐/能效）
+ W8A16（same-base 质量参照，不占 Pareto 名额）。
每 boot：screen dev（HE[0:40]+GSM8K[0:80]）+ holdout（HE[40:]、GSM8K[80:320]、IFEval[0:150]、
XFC 全量）+ needle holdout seeds（Q0/Q1M@128K s2/s5；Q4C/W8 容量降级@32K s2/s5）+ micro。
断点续跑：stages 键 = f"{cand}_B{n}"；boot 间 back-to-back；链首 W0 弃置。
产出 raw/staging/PH4-P3/qualify-report.json。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
sys.path.insert(0, HERE)
from p02_screen import TP2_UUIDS, boot_cmd, stop  # noqa: E402

STAGING = os.path.join(NG, "raw", "staging", "PH4-P3")
PORT = 19702
REPORT = os.path.join(STAGING, "qualify-report.json")
RUNNERS_PY = "/data/tools/vllm29-env/bin/python"
RUN_BASELINE = "/data/compose/qwen27b/eval/run_baseline.py"

CANDS = {
    "Q0":  {"boot": {"tp": 2, "ms": 8, "spec": 1, "kv_dtype": "bfloat16",
                     "model_len": 131072, "nbt": 2048, "patch": "a", "cold": True},
            "needle_pt": 128000, "role": "pareto_shortlist"},
    "Q1M": {"boot": {"tp": 2, "ms": 8, "spec": 1, "kv_dtype": "bfloat16",
                     "model_len": 131072, "nbt": 2048, "patch": "a", "cold": True,
                     "target": "/data/sandbox/nextgen-20260917/quant-artifacts/ph4-q1-mixed"},
            "needle_pt": 128000, "role": "pareto_shortlist"},
    "Q4C": {"boot": {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
                     "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True,
                     "target": "/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a8fp8-dynamic"},
            "needle_pt": 32000, "role": "pareto_shortlist（128K 容量降级@32K）"},
    "W8":  {"boot": {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
                     "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True,
                     "target": "/data/sandbox/nextgen-20260917/quant-artifacts/ph4-w8a16-g128"},
            "needle_pt": 32000, "role": "quality_reference（不占名额）"},
}
BOOTS = 3


def wait_gpu(timeout_s: int = 14400) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used",
                            "--format=csv,noheader"], capture_output=True, text=True)
        used = {ln.split(",")[0].strip(): int(ln.split(",")[1].strip().rstrip(" MiB"))
                for ln in r.stdout.splitlines() if "," in ln}
        if all(used.get(u, 1 << 30) < 1000 for u in TP2_UUIDS.split(",")):
            return
        time.sleep(30)
    raise SystemExit("GPU 等待超时")


def boot_one(cand: str, tag: str):
    b = dict(CANDS[cand]["boot"])
    arm = {"key": f"P3-{cand}-{tag}", "boot": b}
    cmd, btag = boot_cmd(arm, PORT, tag)
    subprocess.run(["rm", "-rf", f"{SBX}/cache-p02-{arm['key'].lower()}"])
    print(f"[{cand}/{tag}] booting ml={b['model_len']}", flush=True)
    r = subprocess.run(["bash", "-c", cmd], timeout=3000)
    log = os.path.join(SBX, f"log-{btag}")
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
        print(f"[{cand}/{tag}] BOOT FAIL", flush=True)
        stop(pgid)
        return None, None, log
    return {"log": log, "pgid": pgid}, pid, log


def rulers(ax: str, args: list, tag: str, api_base: str) -> dict:
    env = dict(os.environ, EVAL_BASE=f"http://127.0.0.1:{PORT}/v1",
               EVAL_MODEL="qwen3.8-27b")
    outp = os.path.join(STAGING, f"rulers-{tag}-{ax}.json")
    r = subprocess.run([RUNNERS_PY, RUN_BASELINE, ax, *args, "--tag", tag],
                       capture_output=True, text=True, timeout=14400, env=env)
    # run_baseline 自身落盘位置未知——捕获 stdout 摘要 + 让它打印（-u）
    return {"rc": r.returncode, "stdout_tail": r.stdout[-600:]}


def needle(api: str, pt: int, seed: int, exp: str) -> dict:
    out = os.path.join(STAGING, exp)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "needle_probe_nextgen.py"),
                        "--api", api, "--prompt-tokens", str(pt), "--seed", str(seed),
                        "--experiment-id", exp, "--out-dir", out,
                        "--max-tokens", "64", "--gpu-uuids", TP2_UUIDS],
                       timeout=1800)
    res = json.load(open(os.path.join(out, "needle-result.json"))) \
        if os.path.exists(os.path.join(out, "needle-result.json")) else {}
    return {"rc": r.returncode, "PASS": res.get("PASS"),
            "needles_hit": res.get("needles_hit"), "ttft_s": res.get("ttft_s")}


def micro(api: str, tag: str) -> dict:
    outp = os.path.join(STAGING, f"micro-{tag}.json")
    r = subprocess.run([sys.executable, os.path.join(HERE, "ph4_tooljson_micro.py"),
                        "--api", api, "--out", outp], capture_output=True, text=True,
                       timeout=1800)
    try:
        return json.load(open(outp))
    except Exception:  # noqa: BLE001
        return {"rc": r.returncode, "tail": r.stdout[-200:]}


def run_boot_phase(cand: str, tag: str) -> dict:
    info, pid, log = boot_one(cand, tag)
    if info is None:
        return {"valid": False, "error": "BOOT_FAIL"}
    api = f"http://127.0.0.1:{PORT}/v1"
    time.sleep(15)
    e = {"info": info, "rulers": {}, "needle_holdout": {}, "micro": None}
    t = f"{cand}-{tag}"
    e["rulers"]["he_screen"] = rulers("humaneval", ["--max", "40"], t, api)
    e["rulers"]["gsm_screen"] = rulers("gsm8k", ["--max", "80"], t, api)
    e["rulers"]["he_holdout"] = rulers("humaneval", ["--skip", "40"], t + "-H", api)
    e["rulers"]["gsm_holdout"] = rulers("gsm8k", ["--skip", "80", "--max", "240"], t + "-H", api)
    e["rulers"]["ifeval_holdout"] = rulers("ifeval", ["--max", "150"], t + "-H", api)
    e["rulers"]["xfc"] = rulers("xfc", [], t + "-H", api)
    for seed in (2, 5):
        e["needle_holdout"][f"s{seed}"] = needle(
            api, CANDS[cand]["needle_pt"], seed, f"P3H-{cand}-{tag}-S{seed}")
    e["micro"] = {k: v for k, v in micro(api, t).items()
                  if k in ("verdict", "n_pass", "n_total")}
    stop(info["pgid"])
    time.sleep(5)
    e["valid"] = True
    return e


def main() -> int:
    os.makedirs(STAGING, exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"stages": {}}
    st = doc["stages"]

    def save():
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)

    if "warmup" not in st:
        wait_gpu()
        info, pid, log = boot_one("Q0", "W0")
        st["warmup"] = {"info": info, "note": "W0 平台暖机弃置"}
        save()
        if info:
            stop(info["pgid"])
        time.sleep(5)

    for cand in CANDS:
        for n in range(1, BOOTS + 1):
            k = f"{cand}_B{n}"
            if k in st and st[k].get("valid"):
                continue
            wait_gpu()
            st[k] = run_boot_phase(cand, f"B{n:02d}")
            st[k]["role"] = CANDS[cand]["role"]
            st[k]["needle_tier"] = CANDS[cand]["needle_pt"]
            save()
    print(json.dumps({k: v.get("valid") for k, v in st.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

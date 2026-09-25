#!/usr/bin/env python3
"""锚点编排器：warmup → thermal-ready（机器判定）→ 正式 reps → 证据收集。

thermal-ready（MANIFEST.yaml thermal_protocol）：
  /metrics 中 running==0 且 waiting==0；NVML 温度在 [25,40]℃ 且偏离基线 <=5℃；
  连续满足 30s 才 ready；最长等 600s，超时 => 退出码 20（ABORTED）。
warmup 使用独立 cache_salt namespace（warmup），不污染正式 prompt。

用法:
  run_arm.py --api http://127.0.0.1:19701/v1 --port 19701 --tp 1 --ms 1 \
    --gpu-uuids GPU-xxx --server-pid P --server-pgid G --tag anchors-tp1 \
    --exp-prefix V28-T1-Q0-KVARN-SD7-MS1-NBT2048-C1-L0565 --runs ns:1 f512:3 \
    --fixture d565 --max-tokens 512
  runs 形如 <mode-key>:<repeats>；mode-key ns=natural-stop(此 max_tokens) f512=fixed-output
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nvml_bind  # noqa: E402

SBX = "/data/sandbox/nextgen-20260917"
THERMAL = {"window": (25, 40), "max_dev_c": 5, "consecutive_s": 30, "max_wait_s": 600}
BASELINE = {2: 29, 3: 28, 4: 29}   # preflight 空闲基线（逻辑卡号）


def get_metrics(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        body = r.read().decode()
    out = {}
    for ln in body.splitlines():
        if ln.startswith("vllm:"):
            parts = ln.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    out[parts[0].split("{")[0]] = float(parts[1])
                except ValueError:
                    pass
    return out


def thermal_ready(api_base: str, watch_uuids: list[str], baseline: dict) -> tuple[bool, str]:
    t0 = time.time()
    ok_since = None
    idx_of = {}
    cards = nvml_bind.snapshot_gpus()
    for c in cards:
        idx_of[c["uuid"]] = c["logical_index"]
    while time.time() - t0 < THERMAL["max_wait_s"]:
        try:
            m = get_metrics(api_base + "/metrics")
            running = m.get("vllm:num_requests_running")
            waiting = m.get("vllm:num_requests_waiting")
        except Exception:  # noqa: BLE001
            running = waiting = None
        cards = nvml_bind.snapshot_gpus()
        temps_ok = True
        detail = []
        for u in watch_uuids:
            c = next((x for x in cards if x["uuid"] == u), None)
            if c is None:
                temps_ok = False
                continue
            base = BASELINE.get(idx_of.get(u, -1), c["temp_c"])
            ok = (THERMAL["window"][0] <= c["temp_c"] <= THERMAL["window"][1]
                  and abs(c["temp_c"] - base) <= THERMAL["max_dev_c"])
            temps_ok = temps_ok and ok
            detail.append(f"{u[-6:]}:{c['temp_c']}C(base{base})")
        idle = (running == 0 and waiting == 0)
        if idle and temps_ok:
            if ok_since is None:
                ok_since = time.time()
            if time.time() - ok_since >= THERMAL["consecutive_s"]:
                return True, f"ready ({','.join(detail)})"
        else:
            ok_since = None
        time.sleep(5)
    return False, f"timeout after {THERMAL['max_wait_s']}s ({','.join(detail)})"


def collect_server_evidence(out_dir: str, port: int, server_pid: int, tag: str) -> None:
    log = os.path.join(SBX, f"log-{tag}", "server.txt")
    if os.path.exists(log):
        subprocess.run(["bash", "-c",
                        f"tail -n 200 {log!r} > {os.path.join(out_dir, 'server-log-tail.txt')!r}"],
                       timeout=30)
    try:
        binding = nvml_bind.bind_pid(server_pid)
    except Exception as e:  # noqa: BLE001
        binding = [{"error": str(e)[:120]}]
    with open(os.path.join(out_dir, "process-uuid-map.json"), "w") as f:
        json.dump({"server_pid": server_pid, "binding": binding}, f, indent=1)
    lc = os.path.join(SBX, f"log-{tag}", "launch-cmd.txt")
    if os.path.exists(lc):
        subprocess.run(["cp", lc, os.path.join(out_dir, "launch-cmd.txt")], timeout=30)


def run_bench(args, exp_id: str, mode: str, out_dir: str, salt_key: str) -> int:
    cmd = [sys.executable, os.path.join(HERE, "bench_nextgen.py"),
           "--api", args.api, "--experiment-id", exp_id,
           "--fixture", args.fixture, "--mode", mode,
           "--concurrency", str(args.concurrency),
           "--max-tokens", str(args.max_tokens),
           "--salt-namespace", "formal", "--salt-key", salt_key,
           "--out-dir", out_dir,
           "--port", str(args.port), "--server-pid", str(args.server_pid),
           "--server-pgid", str(args.server_pgid),
           "--tp", str(args.tp), "--ms", str(args.ms),
           "--cache-root", f"{SBX}/cache-{args.tag}",
           "--gpu-uuids", args.gpu_uuids]
    r = subprocess.run(cmd, timeout=args.max_tokens * 40 + 1800)
    collect_server_evidence(out_dir, args.port, args.server_pid, args.tag)
    return r.returncode


def warmup(args) -> None:
    cmd = [sys.executable, os.path.join(HERE, "bench_nextgen.py"),
           "--api", args.api, "--experiment-id", f"WARMUP-{args.tag}",
           "--fixture", "d565", "--mode", "natural-stop",
           "--concurrency", "1", "--max-tokens", "64",
           "--salt-namespace", "warmup",
           "--out-dir", os.path.join(SBX, f"warmup-{args.tag}-{int(time.time())}"),
           "--port", str(args.port), "--tp", str(args.tp), "--ms", str(args.ms)]
    subprocess.run(cmd, timeout=600)
    print("[warmup] done", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--tp", type=int, required=True)
    ap.add_argument("--ms", type=int, required=True)
    ap.add_argument("--gpu-uuids", required=True)
    ap.add_argument("--server-pid", type=int, required=True)
    ap.add_argument("--server-pgid", type=int, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--exp-prefix", required=True)
    ap.add_argument("--runs", nargs="+", required=True, help="ns:1 f512:3")
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--max-tokens", type=int, required=True)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--skip-thermal", action="store_true")
    ap.add_argument("--warm-prefix", action="store_true",
                    help="正式 runs 用稳定 salt（暖前缀形态，对齐历史 warm 参考值）")
    ap.add_argument("--thermal-api", default=None,
                    help="thermal/metrics 探测端点（Phase 05 router 轨：传 backend API；默认用 --api）")
    ap.add_argument("--boot-tag", default="B01",
                    help="exp_id 的 boot 号（Qualify 3-boot 传 B02/B03；默认 B01 兼容既有证据）")
    args = ap.parse_args()
    uuids = args.gpu_uuids.split(",")

    warmup(args)
    if not args.skip_thermal:
        ok, why = thermal_ready((args.thermal_api or args.api).rsplit("/v1", 1)[0], uuids, BASELINE)
        print(f"[thermal] {why}", flush=True)
        if not ok:
            return 20

    codes = []
    for spec in args.runs:
        key, n = spec.split(":")
        n = int(n)
        mode = "natural-stop" if key == "ns" else "fixed-output"
        salt_key = f"{args.exp_prefix}-{key.upper()}"
        if getattr(args, "warm_prefix", False):
            # 暖前缀形态：与正式 run 完全相同的 salt 先跑一遍（计入 WARM 证据，非正式）
            wid = f"WARMPFX-{salt_key}"
            wdir = os.path.join(NEXTGEN, "raw", "staging", wid)
            os.makedirs(wdir, exist_ok=True)
            cmd = [sys.executable, os.path.join(HERE, "bench_nextgen.py"),
                   "--api", args.api, "--experiment-id", wid,
                   "--fixture", args.fixture, "--mode", mode,
                   "--concurrency", str(args.concurrency),
                   "--max-tokens", "8",
                   "--salt-namespace", "formal", "--salt-key", salt_key,
                   "--out-dir", wdir,
                   "--port", str(args.port), "--tp", str(args.tp), "--ms", str(args.ms)]
            print(f"[warm-prefix] {wid}", flush=True)
            subprocess.run(cmd, timeout=args.max_tokens * 40 + 1800)
            if not args.skip_thermal:
                ok, why = thermal_ready((args.thermal_api or args.api).rsplit("/v1", 1)[0], uuids, BASELINE)
                print(f"[thermal] {why}", flush=True)
                if not ok:
                    return 20
            else:
                print("[thermal] skipped (--skip-thermal): immediate back-to-back warm replay", flush=True)
        for i in range(1, n + 1):
            exp_id = f"{args.exp_prefix}-{key.upper()}-{args.boot_tag}-R{i:02d}"
            out_dir = os.path.join(NEXTGEN, "raw", "staging", exp_id)
            os.makedirs(out_dir, exist_ok=True)
            print(f"[run] {exp_id} mode={mode}", flush=True)
            codes.append((exp_id, run_bench(args, exp_id, mode, out_dir, salt_key)))
    print(json.dumps({"exit_codes": codes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Phase 04 P0B.A — Q4-OFFICIAL 探针（CROSS_BASE_REFERENCE / PROBE_ONLY）。

目的（合同 §七.A）：官方 Qwen3.8-27B-FP8 最小 boot →
  1. kernel/backend 实选取证（server.txt：fp8 路径选择日志）
  2. D565-C1 ×1 + verbatim + tool/JSON micro-suite 冒烟
  3. boot 窗能量采样（NVML，boot 与 serving 分列契约）
死 → UNSUPPORTED 同族取证后停该路（不建 coding 版）；活 → Q4-CODING 构建资格成立。
输出 raw/staging/PH4-P0B/q4-official-probe.json。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NG = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
sys.path.insert(0, HERE)
from p02_screen import TP2_UUIDS, boot_cmd, stop  # noqa: E402
from nvml_bind import NVMLSampler  # noqa: E402

STAGING = os.path.join(NG, "raw", "staging", "PH4-P0B")
PORT = 19702
TARGET = os.environ.get("PH4_TARGET", "/data/models/Qwen3.8-27B-FP8")
REPORT = os.path.join(STAGING, os.environ.get("PH4_REPORT", "q4-official-probe.json"))


def gpu_free() -> bool:
    r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used", "--format=csv,noheader"],
                       capture_output=True, text=True)
    for ln in r.stdout.splitlines():
        parts = [p.strip() for p in ln.split(",")]
        if parts[0] in TP2_UUIDS.split(",") and int(parts[1].rstrip(" MiB")) > 1000:
            return False
    return True


def main() -> int:
    os.makedirs(STAGING, exist_ok=True)
    if not gpu_free():
        print("[q4-probe] GPU3/4 忙——等待重试", flush=True)
        return 1
    boot = {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16",
            "model_len": 36864, "nbt": 2048, "patch": "a", "cold": True,
            "target": TARGET}
    arm = {"key": os.environ.get("PH4_KEY", "PH4-Q4OFF"), "boot": boot}
    cmd, tag = boot_cmd(arm, PORT, "B01")
    subprocess.run(["rm", "-rf", f"{SBX}/cache-p02-ph4-q4off"])
    print(f"[q4-probe] booting official FP8 (29G, TP2)…", flush=True)

    # boot 窗能量采样（与 boot 并行）；结束后转存 jsonl + 梯形积分
    sampler = NVMLSampler(interval_ms=500, uuids=TP2_UUIDS.split(","))
    sampler.start()
    t0 = time.monotonic()
    r = subprocess.run(["bash", "-c", cmd], timeout=2400)
    boot_wall = time.monotonic() - t0
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
    sampler._halt.set()
    sampler.join(timeout=10)
    with open(os.path.join(STAGING, os.environ.get("PH4_NVML", "q4off-boot-nvml.jsonl")), "w") as f:
        for s in sampler.samples:
            f.write(json.dumps(s) + "\n")
    from ph4_energy_report import integrate  # noqa: E402
    from collections import defaultdict  # noqa: E402
    bg: dict[str, list[dict]] = defaultdict(list)
    for s in sampler.samples:
        if isinstance(s.get("t_utc_ns"), int):
            bg[s["uuid"]].append(s)
    boot_energy = integrate(bg) if any(bg) else {
        "note": "samples lack t_utc_ns", "n_samples": len(sampler.samples)}

    doc = {"probe": os.environ.get("PH4_PROBE_NAME", "Q4-OFFICIAL"), "target": TARGET, "boot_rc": r.returncode,
           "boot_wall_s": round(boot_wall, 1),
           "boot_energy": boot_energy,
           "boot_nvml_samples": len(sampler.samples)}
    if r.returncode != 0 or pgid is None:
        doc["verdict"] = "UNSUPPORTED_BOOT_FAIL"
        txt = open(os.path.join(log, "server.txt"), errors="replace").read()[-8000:] \
            if os.path.exists(os.path.join(log, "server.txt")) else ""
        doc["error_tail"] = txt[-3000:]
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
        print("[q4-probe] BOOT FAIL — 取证归档", flush=True)
        stop(pgid)
        return 3

    # kernel 实选取证
    srv = open(os.path.join(log, "server.txt"), errors="replace").read()
    kern = sorted(set(re.findall(
        r"(Using [^\n]{0,120}(?:fp8|FP8|Marlin|CUTLASS|cutlass|triton|scaled)[^\n]{0,60})", srv)))
    doc["kernel_evidence"] = kern[:20]
    doc["quant_config_line"] = [l for l in srv.splitlines() if "quantization=" in l][:1]

    api = f"http://127.0.0.1:{PORT}/v1"
    time.sleep(15)
    # D565-C1 ×1
    from gen_fixtures import make_prompt  # noqa: E402
    import urllib.request  # noqa: E402
    body = json.dumps({"model": "qwen3.8-27b",
                       "messages": [{"role": "user", "content": make_prompt(512)}],
                       "max_tokens": 512, "temperature": 0, "stream": False}).encode()
    req = urllib.request.Request(api + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t1 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            obj = json.loads(resp.read())
        txt = (obj.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        doc["d565_smoke"] = {"ok": True, "wall_s": round(time.monotonic() - t1, 1),
                             "out_tokens": obj.get("usage", {}).get("completion_tokens"),
                             "text_head": txt[:80]}
    except Exception as e:  # noqa: BLE001
        doc["d565_smoke"] = {"ok": False, "err": repr(e)[:150]}

    # verbatim + micro-suite
    vr = subprocess.run([sys.executable, os.path.join(HERE, "verbatim_check.py"),
                         "probe", "--api", api,
                         "--out-dir", os.path.join(STAGING, os.environ.get("PH4_VERB_DIR", "q4off-verbatim")),
                         "--experiment-id", "PH4-Q4OFF-VB"],
                        capture_output=True, text=True, timeout=1200)
    doc["verbatim"] = {"rc": vr.returncode, "tail": (vr.stdout + vr.stderr).strip()[-200:]}
    mr = subprocess.run([sys.executable, os.path.join(HERE, "ph4_tooljson_micro.py"),
                         "--api", api, "--out", os.path.join(STAGING, os.environ.get("PH4_MICRO", "q4off-micro.json"))],
                        capture_output=True, text=True, timeout=1800)
    try:
        doc["micro_suite"] = json.load(open(os.path.join(STAGING, os.environ.get("PH4_MICRO", "q4off-micro.json"))))
    except Exception:  # noqa: BLE001
        doc["micro_suite"] = {"rc": mr.returncode, "tail": mr.stdout[-200:]}

    doc["verdict"] = "ALIVE" if (doc["d565_smoke"].get("ok") and doc["verbatim"]["rc"] == 0
                                 and doc["micro_suite"].get("verdict") == "STRUCTURAL_SAFE") \
        else "PROBE_PARTIAL_REVIEW"
    json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    stop(pgid)
    print(json.dumps({"verdict": doc["verdict"],
                      "kernel": doc["kernel_evidence"][:3],
                      "d565": doc["d565_smoke"].get("ok"),
                      "micro": doc["micro_suite"].get("verdict")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

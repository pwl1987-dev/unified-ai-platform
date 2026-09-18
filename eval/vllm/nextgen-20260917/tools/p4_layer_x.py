#!/usr/bin/env python3
"""P4 Layer X bridge — 0.29 native bf16 KV 长上下文资格（GPU3+4/19702，计划 v1.2）。

背景更新（P1 因果裁决后）：bf16 无召回收益（与 kvarn 等价），Layer X 桥接定位改为
「0.29 native-KV 长上下文能力 + TTFT 配对」，使 KVarN port 止损时 0.29 仍有长上下文 profile。

臂：0.29 + patch(a,b,c) + kv bfloat16 + 220K + spec DFlash2 k=7 + MS1（生产形制）
证据：
  1. 容量：resolved KV token capacity ≥1.05×（从 server 日志）
  2. needle（修正协议=可召回码集）：seed99 + seed2 @220K 各 5/5；
     seed1 已知失败对照（预期 2/5，跨版本确定性等价检查）
  3. TTFT：seed99 ×3 reps；same-KV reference = P1 bf16 104.219s（门 ≤+5%）
  4. MRV2：V2 Model Runner 行
断点续跑：逐项落盘。
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
PY28 = "/data/tools/vllm28-env/bin/python"
OUT_FILE = os.path.join(STAGING, "P4-LAYERX", "layer-x-report.json")
PREFIX = "V29-T2-Q0-KVB16-SD7-MS1-NBT2048-C1-L220K-LX"

from p1_causal import needle, stop, thermal_wait  # noqa: E402


def boot() -> tuple[bool, int | None, str]:
    tag = "lx-b16-220k"
    cmd = (f"cd {HERE} && VLLM_DFLASH2_TORCH_TOPK=1 VLLM_CACHE_ROOT={SBX}/cache-lx-b16 "
           f"setsid bash boot029_nextgen.sh {tag} {PORT} 2 1 "
           f"--kv-dtype bfloat16 --model-len 225280 --spec 1 --patch b --kv-mem auto"
           f" > {SBX}/boot-{tag}.log 2>&1")
    r = subprocess.run(["bash", "-c", cmd], timeout=2400)
    log = os.path.join(SBX, f"log-{tag}")
    pgid = None
    pg = os.path.join(log, "server.pgid")
    if os.path.exists(pg):
        try:
            pgid = int(open(pg).read().strip())
        except Exception:  # noqa: BLE001
            pgid = None
    return r.returncode == 0, pgid, log


def capacity_from_log(log: str) -> dict:
    out = {}
    try:
        for line in open(os.path.join(log, "server.txt"), errors="replace"):
            if "GPU KV cache size" in line:
                out["kv_cache_size_line"] = line.strip()[:200]
                try:
                    out["kv_tokens"] = int(line.split("size:")[1].split("tokens")[0]
                                           .replace(",", "").strip())
                except Exception:  # noqa: BLE001
                    pass
            if "Using V2 Model Runner" in line:
                out["mrv2_proven"] = True
    except FileNotFoundError:
        pass
    return out


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    if not doc.get("boot_done"):
        ready, pgid, log = boot()
        doc["boot_ready"] = ready
        doc["log"] = log
        doc.update(capacity_from_log(log))
        doc["capacity_margin"] = (doc.get("kv_tokens", 0) / 225280
                                  if doc.get("kv_tokens") else None)
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
        if not ready:
            print("[LX] BOOT FAIL — see report", flush=True)
            return 1
        thermal_wait()
        # needle：可召回码集（99/2）+ 已知失败对照（1）
        for seed in (99, 2, 1):
            exp = f"{PREFIX}-S{seed}"
            nr = needle(exp, 220000, seed)
            doc[f"needle_s{seed}"] = {"PASS": nr.get("PASS"), "hits": nr.get("needles_hit"),
                                      "ttft_s": nr.get("ttft_s")}
            print(json.dumps({"seed": seed, "PASS": nr.get("PASS"),
                              "hits": nr.get("needles_hit")}), flush=True)
        # TTFT 3 reps（seed99 同 fixture）
        reps = []
        for r in (1, 2, 3):
            exp = f"{PREFIX}-S99R{r}"
            nr = needle(exp, 220000, 99)
            reps.append(nr.get("ttft_s"))
        doc["ttft_seed99_reps_s"] = reps
        import statistics
        med = statistics.median([x for x in reps if x]) if any(reps) else None
        doc["ttft_median_s"] = med
        doc["ttft_vs_same_kv_reference"] = {
            "reference_028_bf16_s": 104.219,
            "delta_pct": round((med - 104.219) / 104.219 * 100, 3) if med else None,
            "gate_max_pct": 5.0,
        }
        doc["boot_done"] = True
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
        stop(pgid)
        time.sleep(10)
    print(json.dumps({k: doc.get(k) for k in
                      ("capacity_margin", "mrv2_proven", "needle_s99", "needle_s2",
                       "needle_s1", "ttft_median_s", "ttft_vs_same_kv_reference")},
                     ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

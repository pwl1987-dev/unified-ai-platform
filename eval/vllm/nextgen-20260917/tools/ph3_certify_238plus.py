#!/usr/bin/env python3
"""Phase 03 P1 — 238K/245K/262K NATIVE 正式认证链（gates formal_certification_238plus）。

门（冻结）：3 boot × 3 seed（s99/s2/s5）单请求五针全 5/5 ∧ preemptions=0 ∧ OOM=0
∧ TTFT 有效 ∧ 双余量分账落盘（kv_capacity_margin / model_position_margin）。
- 238K/245K：PRODUCTION_SAFE 候选（KV 峰 ≥95% 降 BOUNDARY_PROFILE）
- 262K：全过只标 HARD_CEILING_CAPABILITY_PASS（position 余量 7 token，永不默认工作点）
- 晋级自 Phase 02 CEILING_OBSERVATION；任一不过 → 该档维持 CEILING_OBSERVATION + 原因
断点续跑：stages 键 = f"{tier}_B{n}"；无效观测（rc!=0 ∧ PASS=null）删除重跑。
W0：链首 warmup boot（若上一链 back-to-back 则其亦为快态参照，只记录不计时）。
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
sys.path.insert(0, HERE)
from p02_screen import TP2_UUIDS, boot_cmd, parse_capacity, stop  # noqa: E402

STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19702
REPORT = os.path.join(STAGING, "PH3-KV", "certify-238plus-report.json")

# tier → (model_len, prompt_target)；ph 靶值与 fixtures/manifest-phase03-verification.json 一致
TIERS = {"238k": (243712, 238000), "245k": (251392, 245000), "262k": (262144, 261888)}
SEEDS = (99, 2, 5)
BOOTS = 3
# 离线 tokenizer 装配验证值（P0A.5；model_position_margin = cap − total）
POSITION_MARGIN = {"238k": 5467, "245k": 6151, "262k": 7}
LABEL_ON_PASS = {"238k": "PRODUCTION_SAFE_candidate", "245k": "PRODUCTION_SAFE_candidate",
                 "262k": "HARD_CEILING_CAPABILITY_PASS_only"}


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


def boot_tier(tier: str, tag: str) -> tuple[dict | None, int | None, str]:
    ml = TIERS[tier][0]
    b = {"tp": 2, "ms": 1, "spec": 1, "kv_dtype": "bfloat16",
         "model_len": ml, "nbt": 2048, "patch": "a", "cold": True}
    arm = {"key": f"CERT238P-{tier}-{tag}", "boot": b}
    cmd, btag = boot_cmd(arm, PORT, tag)
    subprocess.run(["rm", "-rf", f"{SBX}/cache-p02-{arm['key'].lower()}"])
    print(f"[{tier}/{tag}] booting model_len={ml}", flush=True)
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
        print(f"[{tier}/{tag}] BOOT FAIL", flush=True)
        stop(pgid)
        return None, pgid, log
    return {"boot_ready": True, "log": log, "pgid": pgid,
            "capacity": parse_capacity(log)}, pgid, log


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


def preempt_oom_from_log(log: str) -> dict:
    txt = open(os.path.join(log, "server.txt"), errors="replace").read()[-60000:]
    pre = re.findall(r"preempt\w*[^\d]*(\d+)", txt, re.I)
    return {"oom_lines": txt.lower().count("out of memory"),
            "preempt_mentions": len(pre)}


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {"stages": {}}
    st = doc["stages"]

    def save() -> None:
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)

    if "warmup" not in st:
        wait_gpu()
        info, pgid, log = boot_tier("238k", "W0")
        st["warmup"] = {"info": info, "note": "W0 平台暖机（不计 evidence boot）"}
        save()
        if pgid:
            stop(pgid)
        time.sleep(5)

    for tier in TIERS:
        for n in range(1, BOOTS + 1):
            k = f"{tier}_B{n}"
            if k in st and not (st[k].get("valid_observation") is False):
                continue
            wait_gpu()
            info, pgid, log = boot_tier(tier, f"B{n:02d}")
            if info is None:
                st[k] = {"valid_observation": False, "error": "BOOT_FAIL"}
                save()
                continue
            entry = {"info": info, "needles": {}}
            api = f"http://127.0.0.1:{PORT}/v1"
            for seed in SEEDS:
                entry["needles"][f"s{seed}"] = needle(
                    api, TIERS[tier][1], seed, f"CERT238P-{tier.upper()}-B{n:02d}-S{seed}")
            entry["preempt_oom"] = preempt_oom_from_log(log)
            needles_valid = all(v.get("PASS") is not None or v.get("rc") != 0
                                for v in entry["needles"].values())
            entry["valid_observation"] = needles_valid
            entry["position_margin_tokens"] = POSITION_MARGIN[tier]
            st[k] = entry
            save()
            stop(pgid)
            time.sleep(5)
    print(json.dumps({k: {"valid": v.get("valid_observation"),
                          "hits": {s: n.get("needles_hit")
                                   for s, n in (v.get("needles") or {}).items()}}
                      for k, v in st.items() if k != "warmup"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

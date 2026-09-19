#!/usr/bin/env python3
"""p02_screen — Phase 02 通用 Screen/Qualify 臂 runner（config 驱动，断点续跑）。

用法:
  python3 p02_screen.py --arms repro/p02-arms/<plan>.json [--only ARM_KEY ...] [--boot-tag B01]

arms JSON 模式（P1/P2/P3 各步生成）:
{
  "port": 19702,
  "arms": [
    {"key": "B0-L32",
     "boot": {"tp": 2, "ms": 4, "spec": 1, "kv_dtype": "bfloat16", "model_len": 32768,
              "nbt": 2048, "cold": true, "patch": "a",
              "cg_mode": null, "cg_cap": 8, "draft_tp": 0, "k": 7, "bss": 0,
              "queued_reqs": null, "queued_tokens": null, "retention": null,
              "match_unit": 128, "pair_uuids": null, "extra": []},
     "cells": [
       {"exp_prefix": "V29-T2-B0L32-SD7-MS4-NBT2048-C1-L0565-F512",
        "fixture": "d565", "mode": "f512", "concurrency": 1, "max_tokens": 512, "reps": 3},
       {"exp_prefix": "...-C4-L0565-NS", "fixture": "d565", "mode": "ns",
        "concurrency": 4, "max_tokens": 512, "reps": 3, "warm_prefix": true}
     ],
     "probes": {"verbatim": true,
                "needle": {"prompt_tokens": 225280, "seeds": [99, 2, 1], "max_tokens": 64}}}
  ]
}

行为：boot（boot029_nextgen.sh，扩展参数）→ 逐 cell 调 run_arm.py（warmup+thermal+reps+五件套）
→ 可选 verbatim/needle → MRV2/容量抓取 → stop(登记 PGID) → 报告 JSON 落 staging（done 标记续跑跳过）。
单变量纪律由 arms JSON 作者负责（paired_axis 显式写在 plan 文档与 exp 前缀里）。
"""
from __future__ import annotations

import argparse
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
VENV_PY = "/data/tools/vllm29-env/bin/python"
TP1_UUID = "GPU-41a1986d-e745-9e40-c520-09490081fd44"
TP2_UUIDS = "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e"


def stop(pgid: int | None) -> None:
    if pgid is None or pgid == os.getpgid(0):
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


def boot_cmd(arm: dict, port: int, boot_tag: str) -> tuple[str, str]:
    b = arm["boot"]
    tag = f"p02-{arm['key'].lower()}-{boot_tag.lower()}"
    # 编译缓存按 arm 键共享（同 arm 3-boot 复用，认证形制=cache 钉死）；log/exp 目录按 boot 分
    cache_key = f"p02-{arm['key'].lower()}"
    env_prefix = " ".join(f"{k}={v}" for k, v in b.get("env", {}).items())
    # extra = 服参（非 boot 脚本旗标）→ EXTRA_SERVE_ARGS 通道（boot 脚本有自己的严格 CLI 解析）
    extra_serve = " ".join(b.get("extra", [])).replace("'", "'\\''")
    if extra_serve:
        env_prefix += f" EXTRA_SERVE_ARGS='{extra_serve}'"
    parts = [f"cd {HERE} && {env_prefix} VLLM_CACHE_ROOT={SBX}/cache-{cache_key} setsid bash boot029_nextgen.sh",
             tag, str(port), str(b["tp"]), str(b["ms"])]
    kv = b.get("kv_dtype") or "auto"
    parts += ["--kv-dtype", kv, "--model-len", str(b.get("model_len", 32768)),
              "--spec", str(b.get("spec", 0)), "--patch", b.get("patch", "a"),
              "--nbt", str(b.get("nbt", 2048)),
              "--cg-cap", str(b.get("cg_cap", 8)),
              "--k", str(b.get("k", 7)),
              "--match-unit", str(b.get("match_unit", 128))]
    if b.get("cg_mode"):
        parts += ["--cg-mode", str(b["cg_mode"])]
    if b.get("draft_tp"):
        parts += ["--draft-tp", str(b["draft_tp"])]
    if b.get("bss"):
        parts += ["--bss", "1"]
    if b.get("queued_reqs") is not None:
        parts += ["--queued-reqs", str(b["queued_reqs"])]
    if b.get("queued_tokens") is not None:
        parts += ["--queued-tokens", str(b["queued_tokens"])]
    if b.get("retention"):
        parts += ["--retention", str(b["retention"])]
    if b.get("pair_uuids"):
        parts += ["--pair-uuids", b["pair_uuids"]]
    # --cold 只在缓存组不存在时生效（同 arm 后续 boot 暖启复用，认证形制）
    if b.get("cold") and not os.path.isdir(f"{SBX}/cache-{cache_key}"):
        parts += ["--cold"]
    if b.get("kv_mem"):
        parts += ["--kv-mem", str(b["kv_mem"])]
    return " ".join(parts), tag


def parse_capacity(log_dir: str) -> dict:
    """从 resolved-kv.txt / server.txt 抓 KV token 容量与 maximum concurrency。"""
    out: dict = {}
    srcs = [os.path.join(log_dir, "resolved-kv.txt"), os.path.join(log_dir, "server.txt")]
    text = ""
    for s in srcs:
        if os.path.exists(s):
            try:
                text += open(s, errors="replace").read()[-20000:]
            except OSError:
                pass
    m = re.search(r"GPU KV cache size[^\d]*([\d,]+)\s*tokens", text)
    if m:
        out["kv_tokens"] = int(m.group(1).replace(",", ""))
    m2 = re.search(r"maximum concurrency[^\d]*([\d,]+)", text)
    if m2:
        out["max_concurrency_reported"] = int(m2.group(1).replace(",", ""))
    m3 = re.search(r"Maximum concurrencyUtilization[^\d]*([\d.]+)", text)
    if m3:
        out["max_concurrency_util"] = float(m3.group(1))
    if "Using V2 Model Runner" in text:
        out["mrv2"] = True
    return out


def run_cell(cell: dict, port: int, arm: dict, tag: str, pgid: int, pid: int,
             boot_tag: str) -> dict:
    uuids = arm["boot"].get("pair_uuids") or (TP2_UUIDS if arm["boot"]["tp"] == 2 else TP1_UUID)
    runs_spec = f"{cell['mode']}:{cell['reps']}"
    cmd = [sys.executable, os.path.join(HERE, "run_arm.py"),
           "--api", f"http://127.0.0.1:{port}/v1", "--port", str(port),
           "--tp", str(arm["boot"]["tp"]), "--ms", str(arm["boot"]["ms"]),
           "--gpu-uuids", uuids, "--server-pid", str(pid), "--server-pgid", str(pgid),
           "--tag", tag, "--exp-prefix", cell["exp_prefix"],
           "--runs", runs_spec, "--fixture", cell["fixture"],
           "--max-tokens", str(cell["max_tokens"]),
           "--concurrency", str(cell["concurrency"]),
           "--boot-tag", boot_tag]
    if cell.get("warm_prefix"):
        cmd.append("--warm-prefix")
    r = subprocess.run(cmd, timeout=cell["max_tokens"] * 60 + 5400)
    rc = r.returncode
    # 空-成功陷阱防线：bench 可能 rc=0 但零请求成功（如 P32K 顶满 model-len 全 400）
    # ——逐 rep 校验 metrics，无效证据记 rc=30，禁止 done=True。
    mode_key = "F512" if cell["mode"] == "f512" else "NS"
    for i in range(1, cell["reps"] + 1):
        md = os.path.join(STAGING,
                          f"{cell['exp_prefix']}-{mode_key}-{boot_tag}-R{i:02d}", "metrics.json")
        try:
            m = json.load(open(md))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("requests_ok", 0) < 1 or m.get("http_errors", 0) > 0
                or m["aggregate"].get("sum_output_tokens", 0) < 1):
            rc = 30
            print(f"[evidence-guard] {md}: requests_ok={m.get('requests_ok')} "
                  f"http_errors={m.get('http_errors')} sum_out={m['aggregate'].get('sum_output_tokens')}"
                  " → 无效证据 rc=30", flush=True)
    return {"rc": rc, "exp_prefix": cell["exp_prefix"], "cell": {
        k: cell[k] for k in ("fixture", "mode", "concurrency", "max_tokens", "reps")}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--boot-tag", default="B01")
    args = ap.parse_args()

    plan = json.load(open(args.arms))
    port = plan.get("port", 19702)
    out_path = os.path.join(STAGING, "P02-SCREEN",
                            os.path.basename(args.arms).replace(".json", "-report.json"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc = json.load(open(out_path)) if os.path.exists(out_path) else {"arms_file": args.arms, "arms": {}}

    for arm in plan["arms"]:
        if args.only and arm["key"] not in args.only:
            continue
        rec_key = f"{arm['key']}-{args.boot_tag}"   # 每 boot 独立 record（3-boot 互不跳过）
        rec = doc["arms"].get(rec_key, {})
        if rec.get("done"):
            print(f"[{rec_key}] done (skip)", flush=True)
            continue
        cmd_str, tag = boot_cmd(arm, port, args.boot_tag)
        log_dir = os.path.join(SBX, f"log-{tag}")
        print(f"[{rec_key}] booting: {cmd_str}", flush=True)
        r = subprocess.run(["bash", "-c", f"{cmd_str} > {SBX}/boot-{tag}.log 2>&1"],
                           timeout=3600)
        if r.returncode != 0:
            rec.update({"done": False, "boot_ready": False, "boot_rc": r.returncode,
                        "log": log_dir, "boot_cmd": cmd_str})
            doc["arms"][rec_key] = rec
            json.dump(doc, open(out_path, "w"), indent=1, ensure_ascii=False)
            print(f"[{rec_key}] BOOT FAIL rc={r.returncode}（配置拒绝=UNSUPPORTED 候选，留证）",
                  flush=True)
            continue
        pgid = int(open(os.path.join(log_dir, "server.pgid")).read().strip())
        pid = int(open(os.path.join(log_dir, "server.pid")).read().strip())
        rec.update({"boot_ready": True, "log": log_dir, "boot_cmd": cmd_str,
                    "pid": pid, "pgid": pgid, "boot_tag": args.boot_tag})
        rec["capacity"] = parse_capacity(log_dir)

        cells_out = rec.get("cells", {})
        for cell in arm.get("cells", []):
            ck = f"{cell['exp_prefix']}-{args.boot_tag}"
            if cells_out.get(ck, {}).get("rc") == 0:
                continue
            print(f"[{rec_key}] cell {ck}", flush=True)
            cells_out[ck] = run_cell(cell, port, arm, tag, pgid, pid, args.boot_tag)
            rec["cells"] = cells_out
            json.dump(doc, open(out_path, "w"), indent=1, ensure_ascii=False)

        probes = arm.get("probes", {})
        pr = rec.get("probes", {})
        if probes.get("verbatim") and "verbatim" not in pr:
            out_v = os.path.join(STAGING, f"{arm['key']}-{args.boot_tag}-VERBATIM")
            rv = subprocess.run([sys.executable, os.path.join(HERE, "verbatim_check.py"),
                                 "probe", "--api", f"http://127.0.0.1:{port}/v1",
                                 "--out", out_v, "--experiment-id",
                                 f"{arm['key']}-{args.boot_tag}-VERBATIM"], timeout=1800)
            pr["verbatim"] = {"rc": rv.returncode, "out": out_v}
            rec["probes"] = pr
            json.dump(doc, open(out_path, "w"), indent=1, ensure_ascii=False)
        for i, seed in enumerate(probes.get("needle", {}).get("seeds", [])):
            nk = f"needle-seed{seed}"
            if nk in pr:
                continue
            nd = probes["needle"]
            out_n = os.path.join(STAGING, f"{arm['key']}-{args.boot_tag}-ND{nd['prompt_tokens']}-S{seed}")
            rn = subprocess.run([VENV_PY, os.path.join(HERE, "needle_probe_nextgen.py"),
                                 "--api", f"http://127.0.0.1:{port}/v1",
                                 "--prompt-tokens", str(nd["prompt_tokens"]),
                                 "--seed", str(seed),
                                 "--experiment-id", f"{arm['key']}-{args.boot_tag}-ND-S{seed}",
                                 "--out-dir", out_n, "--max-tokens", str(nd.get("max_tokens", 64)),
                                 "--gpu-uuids", TP2_UUIDS if arm["boot"]["tp"] == 2 else TP1_UUID],
                                timeout=14400)
            pr[nk] = {"rc": rn.returncode, "out": out_n}
            rec["probes"] = pr
            json.dump(doc, open(out_path, "w"), indent=1, ensure_ascii=False)

        all_ok = (all(c.get("rc") == 0 for c in rec.get("cells", {}).values())
                  and all(p.get("rc") == 0 for p in rec.get("probes", {}).values()))
        rec["done"] = all_ok
        doc["arms"][rec_key] = rec
        json.dump(doc, open(out_path, "w"), indent=1, ensure_ascii=False)
        stop(pgid)
        time.sleep(10)
        print(f"[{rec_key}] done={all_ok} stopped pgid={pgid}", flush=True)

    print(json.dumps({k: {"done": v.get("done"), "boot_ready": v.get("boot_ready"),
                          "cells_ok": sum(1 for c in v.get("cells", {}).values() if c.get("rc") == 0),
                          "cells_total": len(v.get("cells", {}))}
                      for k, v in doc["arms"].items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

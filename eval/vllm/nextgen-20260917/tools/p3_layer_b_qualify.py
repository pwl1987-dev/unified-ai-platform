#!/usr/bin/env python3
"""Layer B Qualify 升级——两版本 spec 臂 B02/B03 补 boot（B01 已有）+ cudagraph 宽采样。

每 boot：ccdet 无损探针 + F512 ×3 + /metrics 全量 gauge 快照（含 graph/dispatch 相关宽匹配）。
Gate 汇总：3-boot TTFT/F512 稳定性 + 无损 3/3 + 接受率分布。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from p3_layer_b import ARMS, boot, metrics_gauges, probe, run_f512, stop  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
STAGING = os.path.join(NEXTGEN, "raw", "staging")
OUT_FILE = os.path.join(STAGING, "P3-LAYERB", "layer-b-qualify.json")


def wide_gauges() -> dict:
    """宽匹配：任何含 graph/dispatch/cudagraph/spec 的 gauge。"""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:19701/metrics", timeout=10) as r:
            body = r.read().decode()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    out = {}
    for ln in body.splitlines():
        if ln.startswith("vllm:") and any(
                k in ln.lower() for k in ("graph", "dispatch", "cudagraph", "spec")):
            parts = ln.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    out[parts[0]] = float(parts[1])
                except ValueError:
                    pass
    return out


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    for arm in ARMS:
        a = doc.setdefault(arm["key"], {})
        for bt in ("B02", "B03"):
            if a.get(bt, {}).get("done"):
                continue
            extra = ("--cudagraph-metrics --per-request-spec-decode-metrics detailed"
                     if arm["ver"] == "29" else "")
            ready, pgid, log = boot(arm["ver"], arm["cache_spec"], f"lbq-{arm['key'].lower()}-{bt}",
                                    spec=1, extra=extra)
            if not ready:
                a[bt] = {"done": False, "log": log}
                json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
                continue
            pid = int(open(os.path.join(log, "server.pid")).read().strip())
            h = probe()
            rc = run_f512(arm["prefix"] + f"-Q{bt}", pgid, pid) if False else 0
            # run_f512 的 exp 前缀已含臂名；boot 号经 --boot-tag
            cmd = [sys.executable, os.path.join(HERE, "run_arm.py"),
                   "--api", "http://127.0.0.1:19701/v1", "--port", "19701",
                   "--tp", "1", "--ms", "1",
                   "--gpu-uuids", "GPU-41a1986d-e745-9e40-c520-09490081fd44",
                   "--server-pid", str(pid), "--server-pgid", str(pgid),
                   "--tag", f"lbq-{arm['key'].lower()}",
                   "--exp-prefix", arm["prefix"],
                   "--runs", "f512:3", "--fixture", "d565", "--max-tokens", "512",
                   "--boot-tag", bt]
            rc = subprocess.run(cmd, timeout=3600).returncode
            g = wide_gauges()
            a[bt] = {"done": rc == 0, "hash_spec": h, "log": log,
                     "wide_gauges": dict(list(g.items())[:20])}
            json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
            stop(pgid)
            time.sleep(10)
    json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: {b: x.get("done") for b, x in v.items() if isinstance(x, dict)}
                      for k, v in doc.items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

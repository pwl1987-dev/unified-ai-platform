#!/usr/bin/env python3
"""Phase 03 P1 — KVARN 0.28 CROSS_RUNTIME_REFERENCE 参考臂。

gates-phase03 kv_routes.kvarn_028（用户拍板）：
  - runtime = vllm28-env + boot028_nextgen.sh（0.28 生产认证冻结配方，max_model_len=245760 不改）
  - 三禁令：不算同栈 winner 加速比；行485 tie-break 不跨版本套用；262K 越域只标
    out_of_domain（不判质量 FAIL）
  - 数据点：D565-F512-C1 ×3（参考吞吐）+ needle s99 @224K/238K/245K（各 5 针）
    + 容量快照（kvarn 池）；全部标 cross_runtime_reference=KVARN_K4V2_G128@0.28
  - ms=8（C1/needle 形制下不影响 KV 行为；选择记录入 manifest 注记）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
sys.path.insert(0, HERE)
from gen_fixtures import make_needle_fixture  # noqa: E402 （d565 用 make_prompt 同源）
from p02_screen import TP2_UUIDS  # noqa: E402

STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19702
REPORT = os.path.join(STAGING, "PH3-KV", "kvarn-ref-report.json")
XREF = {"cross_runtime_reference": True, "runtime": "0.28+kvarn（vllm28-env 只读）",
        "kv_route": "KVARN_K4V2_G128", "frozen_recipe_max_model_len": 245760,
        "forbidden_claims": ["同栈 winner 加速比", "行485 tie-break 跨版本", "262K 越域质量 FAIL"]}

NEEDLE_TARGETS = ((224, 224000), (238, 238000), (245, 245000))   # (k, prompt_target)


def http_json(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read())


def stream_chat(api: str, content: str, max_tokens: int, timeout: int = 1200) -> dict:
    body = json.dumps({"model": "qwen3.8-27b", "messages": [{"role": "user", "content": content}],
                       "max_tokens": max_tokens, "temperature": 0, "stream": False}).encode()
    req = urllib.request.Request(api + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.loads(r.read())
    txt = (obj.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    return {"ttft_wall": time.monotonic() - t0, "text": txt,
            "usage": obj.get("usage", {})}


def needle5(api: str, prompt_target: int, seed: int, tag: str) -> dict:
    """单请求协议（needle_probe_nextgen：一次问全 5 码，PASS=5/5）——与 Phase 01/02 同源。"""
    out = os.path.join(STAGING, "PH3-KV", f"ND-{tag}")
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "needle_probe_nextgen.py"),
                        "--api", api, "--prompt-tokens", str(prompt_target),
                        "--seed", str(seed), "--experiment-id", f"ND-{tag}",
                        "--out-dir", out, "--max-tokens", "64",
                        "--gpu-uuids", TP2_UUIDS],
                       timeout=1800)
    res = {}
    rp = os.path.join(out, "needle-result.json")
    if os.path.exists(rp):
        res = json.load(open(rp))
    print(f"[needle {tag}] rc={r.returncode} hit={res.get('needles_hit')} ttft={res.get('ttft_s')}", flush=True)
    return {"rc": r.returncode, "PASS": res.get("PASS"),
            "needles_hit": res.get("needles_hit"), "ttft_s": res.get("ttft_s")}


def d565_c1(api: str, reps: int = 3) -> dict:
    sys.path.insert(0, HERE)
    from gen_fixtures import make_prompt
    p = make_prompt(512)
    ttfts, toks = [], []
    for i in range(reps):
        t0 = time.monotonic()
        r = stream_chat(api, p, 512)
        wall = time.monotonic() - t0
        out_tok = r["usage"].get("completion_tokens", 0)
        ttfts.append(r["ttft_wall"])
        toks.append(out_tok / wall if wall else 0)
        print(f"[d565] rep{i+1} wall={wall:.1f}s tok/s={out_tok/wall:.1f}", flush=True)
    return {"reps": reps, "ttft_wall_s": ttfts, "tok_s_median": sorted(toks)[len(toks)//2]}


def main() -> int:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    doc = json.load(open(REPORT)) if os.path.exists(REPORT) else {}
    if doc.get("done"):
        print("[kvarn-ref] already done")
        return 0
    tag = "PH3-KVARN28-B01"
    cmd = (f"cd {HERE} && setsid bash boot028_nextgen.sh {tag} {PORT} 2 8")
    print(f"[kvarn-ref] booting 0.28 frozen recipe (tp2 ms8)", flush=True)
    r = subprocess.run(["bash", "-c", cmd], timeout=2400)
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
        doc.update({"done": False, "error": "BOOT_FAIL", "boot_rc": r.returncode})
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
        return 1
    doc.update({"boot": {"tag": tag, "log": log, "pgid": pgid}, "xref": XREF})
    # 容量快照（kvarn 池 tokens）
    srv = open(os.path.join(log, "server.txt"), errors="replace").read()[-30000:]
    m = re.search(r"GPU KV cache size[^\d]*([\d,]+)\s*tokens", srv)
    doc["capacity"] = {"kv_tokens_kvarn": int(m.group(1).replace(",", "")) if m else None}
    api = f"http://127.0.0.1:{PORT}/v1"
    doc["d565_c1"] = d565_c1(api)
    doc["needles"] = {}
    for k, pt in NEEDLE_TARGETS:
        doc["needles"][f"p{k}k"] = needle5(api, pt, 99, f"P{k}K-S99")
        json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    doc["done"] = True
    doc["out_of_domain_marks"] = {"262k": "不在 frozen 0.28 recipe 能力域（max_model_len=245760）——非质量 FAIL"}
    json.dump(doc, open(REPORT, "w"), indent=1, ensure_ascii=False)
    # 清场：本臂自有 PGID
    try:
        os.killpg(pgid, 15)
    except OSError:
        pass
    print("[kvarn-ref] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

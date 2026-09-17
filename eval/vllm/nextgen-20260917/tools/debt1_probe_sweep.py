#!/usr/bin/env python3
"""D1 补扫：确定性探针横扫 3 个 cache 组（同 root 复用态 boot）。

背景：原 debt_compile_cache.py 的探针结果只存 runner 内存，历次 runner 被
会话重启收割后丢失（9 步 bench 证据完好，仅探针丢失）。本脚本对每组
cache root 复用 boot 一次，跑固定探针（与原脚本同题同参同 salt），
结果立即落盘 {SBX}/cc-{g}-probe.json，按组断点续跑。

判定（与 gates D1 对齐，覆盖度=每组复用态 1 针，共 3 针）：
PASS = 3 组各 1 针且 sha256 全一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
VENV = "/data/tools/vllm28-env"
PORT = 19701
TP1_UUID = "GPU-41a1986d-e745-9e40-c520-09490081fd44"

PROBE_PY = (
    "import json,urllib.request,hashlib,os\n"
    "payload={'model':'qwen3.8-27b','temperature':0,'seed':4242,"
    "'chat_template_kwargs':{'enable_thinking':False},"
    "'messages':[{'role':'user','content':'请逐字输出：NEXTGEN-CCDET-CHECK-7f3a。'}],"
    "'max_tokens':24,'stream':False,'cache_salt':'ccdet-fixed-7f3a'}\n"
    "req=urllib.request.Request(os.environ['DET_API']+'/chat/completions',"
    "data=json.dumps(payload).encode(),"
    "headers={'Content-Type':'application/json'})\n"
    "obj=json.load(urllib.request.urlopen(req,timeout=120))\n"
    "text=(obj.get('choices') or [{}])[0].get('message',{}).get('content') or ''\n"
    "u=obj.get('usage') or {}\n"
    "print(json.dumps({'text_sha256':hashlib.sha256(text.encode()).hexdigest(),"
    "'completion_tokens':u.get('completion_tokens'),'head':text[:40]}))\n"
)


def probe() -> dict:
    r = subprocess.run([os.path.join(VENV, "bin", "python"), "-c", PROBE_PY],
                       capture_output=True, text=True,
                       env={**os.environ, "DET_API": f"http://127.0.0.1:{PORT}/v1"})
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": (r.stderr or r.stdout)[-200:]}


def stop(pgid: int) -> None:
    if pgid == os.getpgid(0):
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


def main() -> int:
    results = {}
    for g in ("g1", "g2", "g3"):
        out_f = f"{SBX}/cc-{g}-probe.json"
        if os.path.exists(out_f):
            results[g] = json.load(open(out_f)).get("probe")
            print(f"[{g}] resumed: {results[g]}", flush=True)
            continue
        tag = f"cc-{g}-probe"
        subprocess.run(["bash", "-c",
                        f"cd {HERE} && VLLM_CACHE_ROOT={SBX}/cache-cc-{g} "
                        f"setsid bash boot028_nextgen.sh {tag} {PORT} 1 1 "
                        f"> {SBX}/boot-{tag}.log 2>&1"], timeout=2400)
        for _ in range(480):
            r = subprocess.run(["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
                                f"http://127.0.0.1:{PORT}/health"],
                               capture_output=True, text=True)
            if r.stdout.strip() == "200":
                break
            time.sleep(5)
        log = os.path.join(SBX, f"log-{tag}")
        pid = int(open(os.path.join(log, "server.pid")).read().strip())
        pgid = int(open(os.path.join(log, "server.pgid")).read().strip())
        p = probe()
        json.dump({"group": g, "probe": p,
                   "utc": time.time(), "pid": pid},
                  open(out_f, "w"), indent=1)          # 立即落盘
        results[g] = p
        print(f"[{g}] {json.dumps(p, ensure_ascii=False)}", flush=True)
        stop(pgid)
        time.sleep(5)
    shas = [r.get("text_sha256") for r in results.values() if r]
    verdict = ("PASS" if len(shas) >= 3 and len(set(shas)) == 1 else
               "CHECK" if shas else "NO_PROBES")
    out = os.path.join(NEXTGEN, "raw", "staging", "DEBT1-COMPILE-CACHE")
    os.makedirs(out, exist_ok=True)
    json.dump({"probes": results, "verdict": verdict,
               "coverage": "restart-state probe per independent cold cache group"},
              open(os.path.join(out, "debt1-determinism.json"), "w"),
              indent=1, ensure_ascii=False)
    print(f"DEBT1_PROBE_{verdict} n={len(shas)} unique={len(set(shas))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

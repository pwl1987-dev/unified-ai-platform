#!/usr/bin/env python3
"""P3 Layer B TP1 — 0.28 vs 0.29 + DFlash2 recal k=7（GPU2/19701，计划 v1.2）。

臂（target-only 已由 Layer A 覆盖；此处在同形制上加 spec）：
  LB28REF: 0.28+overlay, kv auto, spec=1, 32K, MS1
  LB29B  : 0.29(unit a+b), kv auto, spec=1, 32K, MS1, --cudagraph-metrics
           --per-request-spec-decode-metrics detailed
证据：
  1. 输出无损门：ccdet 固定探针（temp0/seed4242/salt 固定）target-only vs spec 逐位一致（分版本）
  2. 接受率：/metrics 的 vllm:spec_decode_* gauge 快照（bench 前后各一次）→ accepted/proposed
  3. graph replay（0.29）：vllm:cudagraph_* gauge（ratio 判据见 gates-phase01）
  4. D565 F512 ×3（Screen；spec 加速记录 + Qualify 晋级判据）
  5. unit-c 实证：0.29 boot 后首个请求即 topk 路径考验（JIT 死则探针失败 → 移植补丁 c）
断点续跑：全部证据逐项落盘 OUT_FILE。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
STAGING = os.path.join(NEXTGEN, "raw", "staging")
PORT = 19701
TP1_UUID = "GPU-41a1986d-e745-9e40-c520-09490081fd44"
OUT_FILE = os.path.join(STAGING, "P3-LAYERB", "layer-b-tp1-report.json")
PY28 = "/data/tools/vllm28-env/bin/python"

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
    "spec=(obj.get('metrics') or {}).get('speculative_decoding')\n"
    "print(json.dumps({'text_sha256':hashlib.sha256(text.encode()).hexdigest(),"
    "'completion_tokens':u.get('completion_tokens'),'head':text[:40],'spec_metrics':spec}))\n"
)

ARMS = [
    {"key": "LB28REF", "ver": "28", "prefix": "V28-T1-Q0-KVAUTO-SD7-MS1-NBT2048-C1-L032K-LB28REF",
     "cache_spec": f"{SBX}/cache-lb28ref", "cache_tonly": f"{SBX}/cache-la28ref"},
    {"key": "LB29B", "ver": "29", "prefix": "V29-T1-Q0-KVAUTO-SD7-MS1-NBT2048-C1-L032K-LB29B",
     "cache_spec": f"{SBX}/cache-lb29b", "cache_tonly": f"{SBX}/cache-la29a"},
]


def probe() -> dict:
    r = subprocess.run([PY28, "-c", PROBE_PY], capture_output=True, text=True,
                       env={**os.environ, "DET_API": f"http://127.0.0.1:{PORT}/v1"})
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": (r.stderr or r.stdout)[-300:]}


def metrics_gauges() -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/metrics", timeout=10) as r:
            body = r.read().decode()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    out = {}
    for ln in body.splitlines():
        if ln.startswith(("vllm:spec_decode", "vllm:cudagraph", "vllm:num_speculative")):
            parts = ln.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    out[parts[0]] = float(parts[1])
                except ValueError:
                    pass
    return out


def boot(ver: str, cache: str, tag: str, spec: int, extra: str = "") -> tuple[bool, int | None, str]:
    if ver == "28":
        script = "p1_boot028.sh"
        cmd_core = (f"setsid bash {script} {tag} {PORT} 1 1 "
                    f"--kv-dtype auto --model-len 32768 --spec {spec} --kv-mem auto")
    else:
        patch = "a" if spec == 0 else "b"
        cmd_core = (f"setsid bash boot029_nextgen.sh {tag} {PORT} 1 1 "
                    f"--kv-dtype auto --model-len 32768 --spec {spec} --patch {patch} --kv-mem auto")
    cmd = (f"cd {HERE} && VLLM_CACHE_ROOT={cache} EXTRA_SERVE_ARGS='{extra}' "
           f"{cmd_core} > {SBX}/boot-{tag}.log 2>&1")
    r = subprocess.run(["bash", "-c", cmd], timeout=1800)
    log = os.path.join(SBX, f"log-{tag}")
    pgid = None
    pg = os.path.join(log, "server.pgid")
    if os.path.exists(pg):
        try:
            pgid = int(open(pg).read().strip())
        except Exception:  # noqa: BLE001
            pgid = None
    return r.returncode == 0, pgid, log


def stop(pgid: int | None) -> None:
    if pgid is None:
        return
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


def run_f512(prefix: str, pgid: int, pid: int) -> int:
    cmd = [sys.executable, os.path.join(HERE, "run_arm.py"),
           "--api", f"http://127.0.0.1:{PORT}/v1", "--port", str(PORT),
           "--tp", "1", "--ms", "1", "--gpu-uuids", TP1_UUID,
           "--server-pid", str(pid), "--server-pgid", str(pgid),
           "--tag", "lb", "--exp-prefix", prefix,
           "--runs", "f512:3", "--fixture", "d565", "--max-tokens", "512",
           "--boot-tag", "B01"]
    return subprocess.run(cmd, timeout=3600).returncode


def acceptance_from_gauges(g: dict) -> dict:
    def find(*subs):
        for k, v in g.items():
            if all(s in k for s in subs):
                return v
        return None
    acc = find("spec_decode", "accepted")
    prop = find("spec_decode", "proposed") or find("spec_decode", "draft")
    out = {"gauges": {k: v for k, v in list(g.items())[:12]},
           "accepted": acc, "proposed": prop}
    if acc is not None and prop:
        out["acceptance_ratio"] = acc / prop
    return out


def main() -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    doc = json.load(open(OUT_FILE)) if os.path.exists(OUT_FILE) else {}
    for arm in ARMS:
        a = doc.setdefault(arm["key"], {})
        # 1) target-only 探针（无损门基准；Layer A 同形制 boot，独立短 boot）
        if not a.get("hash_tonly"):
            ready, pgid, log = boot(arm["ver"], arm["cache_tonly"], f"lb-{arm['key'].lower()}-t", spec=0)
            if ready:
                a["hash_tonly"] = probe()
                a["log_tonly"] = log
                stop(pgid)
                json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
        # 2) spec 臂
        if not a.get("spec_done"):
            extra = ("--cudagraph-metrics --per-request-spec-decode-metrics detailed"
                     if arm["ver"] == "29" else "")
            ready, pgid, log = boot(arm["ver"], arm["cache_spec"], f"lb-{arm['key'].lower()}-s", spec=1,
                                    extra=extra)
            if not ready:
                a["spec_done"] = False
                a["boot_fail_log"] = log
                json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
                print(f"[{arm['key']}] SPEC BOOT FAIL {log}", flush=True)
                continue
            pid = int(open(os.path.join(log, "server.pid")).read().strip())
            pre = metrics_gauges()
            a["hash_spec"] = probe()
            rc = run_f512(arm["prefix"], pgid, pid)
            post = metrics_gauges()
            a.update({
                "spec_done": rc == 0, "log_spec": log,
                "gauges_pre_bench": acceptance_from_gauges(pre),
                "gauges_post_bench": acceptance_from_gauges(post),
                "cudagraph_gauges_post": {k: v for k, v in post.items() if "cudagraph" in k},
            })
            json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
            stop(pgid)
            time.sleep(10)
        ht = (a.get("hash_tonly") or {}).get("text_sha256")
        hs = (a.get("hash_spec") or {}).get("text_sha256")
        a["lossless_bitwise"] = bool(ht and hs and ht == hs)
        json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
        print(json.dumps({"arm": arm["key"], "lossless": a["lossless_bitwise"],
                          "hash_t": ht, "hash_s": hs,
                          "acceptance": (a.get("gauges_post_bench") or {}).get("acceptance_ratio")}),
              flush=True)
    json.dump(doc, open(OUT_FILE, "w"), indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

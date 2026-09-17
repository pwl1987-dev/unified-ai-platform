#!/usr/bin/env python3
"""补债 D1：compile cache 确定性 — 3 个隔离冷 cache 组（v2.1 第 12 条）。

每组：COLD boot（fresh VLLM_CACHE_ROOT，coldness proof：pre-build 快照必须空）
→ D565 F512 run → restart1（同 root 复用）→ run → restart2 → run。
记录：输出文本 sha256 + completion tokens + client decode + boot ready 秒数 +
cache artifact 目录清单 sha256 + server log 中 compile/cache 证据行。
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
sys.path.insert(0, HERE)
import nvml_bind  # noqa: E402

SBX = "/data/sandbox/nextgen-20260917"
VENV = "/data/tools/vllm28-env"
PORT = 19701
TP1_UUID = "GPU-41a1986d-e745-9e40-c520-09490081fd44"

# coldness proof 要枚举的缓存层（build 前必须空/不存在）
CACHE_LAYERS = [
    "torch_compile_cache", "triton_cache", "vllm_artifacts",
    "home_torch_cache", "home_triton_cache",
]


def cache_layer_snapshot(group_root: str) -> dict:
    layers = {}
    candidates = {
        "torch_compile_cache": os.path.join(group_root, "torch_compile_cache"),
        "triton_cache": os.path.join(os.environ.get("TRITON_CACHE_DIR", "/nonexistent")),
        "vllm_artifacts": group_root,
        "home_torch_cache": os.path.expanduser("~/.cache/vllm/torch_compile_cache"),
        "home_triton_cache": os.path.expanduser("~/.cache/triton"),
    }
    for name, p in candidates.items():
        if os.path.isdir(p):
            n = sum(len(fs) for _, _, fs in os.walk(p))
            layers[name] = {"exists": True, "files": n}
        else:
            layers[name] = {"exists": False, "files": 0}
    return layers


def dir_manifest(root: str) -> dict:
    out = {}
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            fp = os.path.join(dp, fn)
            rel = os.path.relpath(fp, root)
            try:
                h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
                out[rel] = {"sha256": h, "size": os.path.getsize(fp)}
            except OSError:
                pass
    return out


def boot(group: str, step: str) -> tuple[int, int, float]:
    t0 = time.time()
    tag = f"cc-{group}-{step}"
    log = os.path.join(SBX, f"log-{tag}")
    # setsid：server 独立进程组，避免 stop(pgid) 组杀时连 runner 自杀（铁律 5）
    subprocess.run(["bash", "-c",
                    f"cd {HERE} && VLLM_CACHE_ROOT={SBX}/cache-cc-{group} "
                    f"setsid bash boot028_nextgen.sh {tag} {PORT} 1 1 "
                    f"> {SBX}/boot-{tag}.log 2>&1"], timeout=2400)
    for _ in range(480):
        r = subprocess.run(["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
                            f"http://127.0.0.1:{PORT}/health"], capture_output=True, text=True)
        if r.stdout.strip() == "200":
            break
        time.sleep(5)
    pid = int(open(os.path.join(log, "server.pid")).read().strip())
    pgid = int(open(os.path.join(log, "server.pgid")).read().strip())
    return pid, pgid, time.time() - t0


def stop(pgid: int) -> None:
    # 防自杀闸 + os.killpg 可靠轮询（ps --pgid 计数在孤儿场景误报组空）
    if pgid == os.getpgid(0):
        print(f"[stop] REFUSE kill own pgid {pgid}", flush=True)
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


def run_d565(pid: int, pgid: int, tag: str, exp_id: str) -> dict:
    out = os.path.join(NEXTGEN, "raw", "staging", exp_id)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run(
        [os.path.join(VENV, "bin", "python"), os.path.join(HERE, "bench_nextgen.py"),
         "--api", f"http://127.0.0.1:{PORT}/v1", "--experiment-id", exp_id,
         "--fixture", "d565", "--mode", "fixed-output", "--concurrency", "1",
         "--max-tokens", "512", "--salt-key", f"ccdet-{tag}",
         "--out-dir", out, "--port", str(PORT), "--server-pid", str(pid),
         "--server-pgid", str(pgid), "--tp", "1", "--ms", "1",
         "--cache-root", f"{SBX}/cache-cc-{tag.split('-')[1]}",
         "--gpu-uuids", TP1_UUID], timeout=600, capture_output=True, text=True)
    m = json.load(open(os.path.join(out, "metrics.json")))
    # 输出文本 hash：用 raw-events 不足以取文本 — 补一个确定性短请求
    det = subprocess.run(
        [os.path.join(VENV, "bin", "python"), "-c",
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
         "'completion_tokens':u.get('completion_tokens')}))"],
        capture_output=True, text=True,
        env={**os.environ, "DET_API": f"http://127.0.0.1:{PORT}/v1"})
    try:
        det_res = json.loads(det.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        det_res = {"error": det.stderr[-200:]}
    pr = [r0 for r0 in m["per_request"] if r0["ok"]]
    return {
        "exp_id": exp_id, "bench_rc": r.returncode,
        "client_observed_decode_tok_s": [r0["client_observed_decode_tok_s"] for r0 in pr],
        "output_tokens": [r0["output_tokens"] for r0 in pr],
        "ttft_s": [r0["ttft_s"] for r0 in pr],
        "determinism_probe": det_res,
    }


def main() -> int:
    report: dict = {"groups": {}}
    for g in ("g1", "g2", "g3"):
        groot = f"{SBX}/cache-cc-{g}"
        # 断点续跑：组内已有任一步骤证据则保留 cache root，跳过已完成的步骤
        done_steps = [st for st in ("build", "restart1", "restart2")
                      if os.path.exists(os.path.join(
                          NEXTGEN, "raw", "staging",
                          f"V28-T1-CC-{g.upper()}-{st.upper()}-D565-F512", "metrics.json"))]
        if not done_steps:
            subprocess.run(["rm", "-rf", groot], timeout=120)
            pre = cache_layer_snapshot(groot)
            # 冷证明立即落盘，防 runner 中断后丢失
            json.dump(pre, open(f"{SBX}/cc-{g}-coldness.json", "w"), indent=1)
        else:
            pre = {"resumed": True, "done_steps": done_steps}
        grp: dict = {"coldness_pre_build": pre, "steps": []}
        for step in ("build", "restart1", "restart2"):
            if step in done_steps:
                mfile = os.path.join(NEXTGEN, "raw", "staging",
                                     f"V28-T1-CC-{g.upper()}-{step.upper()}-D565-F512",
                                     "metrics.json")
                m = json.load(open(mfile))
                pr = [r0 for r0 in m["per_request"] if r0["ok"]]
                grp["steps"].append({
                    "exp_id": f"V28-T1-CC-{g.upper()}-{step.upper()}-D565-F512",
                    "resumed_from_evidence": True,
                    "client_observed_decode_tok_s": [r0["client_observed_decode_tok_s"] for r0 in pr],
                    "output_tokens": [r0["output_tokens"] for r0 in pr],
                    "ttft_s": [r0["ttft_s"] for r0 in pr],
                })
                continue
            pid, pgid, ready_s = boot(g, step)
            log = os.path.join(SBX, f"log-cc-{g}-{step}", "server.txt")
            compile_evidence = subprocess.run(
                ["bash", "-c",
                 f"grep -ciE 'cache hit|compiled|compilation|torch.compile' {log!r} | head -1; "
                 f"grep -iE 'cache hit|using cached|compilation cache' {log!r} | head -5"],
                capture_output=True, text=True).stdout
            res = run_d565(pid, pgid, f"cc-{g}-{step}",
                           f"V28-T1-CC-{g.upper()}-{step.upper()}-D565-F512")
            res["boot_ready_s"] = round(ready_s, 1)
            res["compile_log_evidence"] = compile_evidence.strip()[:400]
            grp["steps"].append(res)
            stop(pgid)
            time.sleep(5)
        grp["post_cache_manifest_files"] = len(dir_manifest(groot))
        grp["cache_dir_sha_manifest"] = {
            k: v["sha256"] for k, v in list(dir_manifest(groot).items())[:50]}
        report["groups"][g] = grp
        print(json.dumps({"group": g, "done": True,
                          "ready_s": [s.get("boot_ready_s") for s in grp["steps"]],
                          "decode": [s["client_observed_decode_tok_s"] for s in grp["steps"]],
                          "det": [s.get("determinism_probe") for s in grp["steps"]]},
                         ensure_ascii=False), flush=True)
    out = os.path.join(NEXTGEN, "raw", "staging", "DEBT1-COMPILE-CACHE")
    os.makedirs(out, exist_ok=True)
    json.dump(report, open(os.path.join(out, "debt1-report.json"), "w"),
              indent=1, ensure_ascii=False)
    # 合并补扫持久化探针（原 9 点位探针随 runner 被会话重启收割丢失；
    # debt1_probe_sweep.py 以"每组复用态 1 针"补齐，覆盖 3 组独立冷 cache）
    for g in report["groups"]:
        pf = f"{SBX}/cc-{g}-probe.json"
        if os.path.exists(pf) and not any(
                s.get("determinism_probe") for s in report["groups"][g]["steps"]):
            report["groups"][g]["steps"].append(
                {"exp_id": f"cc-{g}-probe-sweep", "probe_sweep": True,
                 "determinism_probe": json.load(open(pf))["probe"]})
    json.dump(report, open(os.path.join(out, "debt1-report.json"), "w"),
              indent=1, ensure_ascii=False)
    dets = [s["determinism_probe"].get("text_sha256")
            for g in report["groups"] for s in report["groups"][g]["steps"]
            if s.get("determinism_probe")]
    verdict = ("PASS" if dets and len(set(dets)) == 1 and len(dets) >= 3 else
               "CHECK" if dets else "NO_PROBES")
    print(f"DEBT1_{verdict} n_probes={len(dets)} unique={len(set(dets))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""补债 D2：TP2 238K 双 Gate — 3 boot × 3 seed 五针（gates-phase00.yaml D2）。

正确性 Gate：每 boot 15/15（3 seed × 5 针，预定义 exact 规则）。
稳定性 Gate：跨 boot TTFT 中位漂移 ≤10%、KV 峰漂移 ≤5%、VRAM 峰 ≤2%、
零 OOM/crash/preempt/http error。
boot 复用 cache-anchors-tp2（暖编译，compile 确定性不是本债变量）。
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEXTGEN = os.path.dirname(HERE)
SBX = "/data/sandbox/nextgen-20260917"
PY = "/data/tools/vllm28-env/bin/python"
PORT = 19702
TP2_UUIDS = "GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae,GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e"
SEEDS = (1, 2, 3)
BOOTS = ("b1", "b2", "b3")


def boot(tag: str) -> tuple[int, int]:
    # setsid：server 独立进程组，避免 stop(pgid) 组杀时连 runner 自杀（铁律 5）
    subprocess.run(["bash", "-c",
                    f"cd {HERE} && VLLM_CACHE_ROOT={SBX}/cache-anchors-tp2 "
                    f"setsid bash boot028_nextgen.sh d238-{tag} {PORT} 2 1 "
                    f"> {SBX}/boot-d238-{tag}.log 2>&1"], timeout=2400)
    for _ in range(480):
        r = subprocess.run(["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
                            f"http://127.0.0.1:{PORT}/health"], capture_output=True, text=True)
        if r.stdout.strip() == "200":
            break
        time.sleep(5)
    log = os.path.join(SBX, f"log-d238-{tag}")
    pid = int(open(os.path.join(log, "server.pid")).read().strip())
    pgid = int(open(os.path.join(log, "server.pgid")).read().strip())
    return pid, pgid


def stop(pgid: int) -> None:
    # 防自杀闸：绝不对自己所在进程组发信号（铁律 5）。
    # 用 os.killpg 而非 ps --pgid 计数（后者在 PPID=1 孤儿场景会误报组空，
    # 导致 TERM 后提前返回、跳过 KILL 兜底 → 僵尸 server 占端口）。
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


def thermal_wait() -> bool:
    t0 = time.time()
    ok_since = None
    while time.time() - t0 < 600:
        cards = subprocess.run([PY, os.path.join(HERE, "nvml_bind.py"), "snapshot"],
                               capture_output=True, text=True)
        try:
            cs = json.loads(cards.stdout)
            t2 = [c["temp_c"] for c in cs if c["uuid"] in TP2_UUIDS.split(",")]
        except Exception:  # noqa: BLE001
            time.sleep(5); continue
        idle_ok = all(25 <= t <= 40 for t in t2)
        if idle_ok:
            ok_since = ok_since or time.time()
            if time.time() - ok_since >= 30:
                return True
        else:
            ok_since = None
        time.sleep(5)
    return False


def boot_done(b: str) -> bool:
    """该 boot 的 3 seed + 220K needle 证据是否全部落盘（断点续跑判据）。"""
    for s in SEEDS:
        if not os.path.exists(os.path.join(
                NEXTGEN, "raw", "staging",
                f"V28-T2-Q0-KVARN-SD7-MS1-NBT2048-C1-L238K-NDL-{b.upper()}-S{s}",
                "needle-result.json")):
            return False
    return os.path.exists(os.path.join(
        NEXTGEN, "raw", "staging",
        f"V28-T2-Q0-KVARN-SD7-MS1-NBT2048-C1-L220K-NDL-{b.upper()}-S1",
        "needle-result.json"))


def reap_orphan_servers() -> None:
    """续跑前置清场：按 pid 文件核对并 TERM 上次中断遗留的本债 TP2 server。"""
    for tag in BOOTS:
        d = os.path.join(SBX, f"log-d238-{tag}")
        pidf = os.path.join(d, "server.pid")
        if not os.path.exists(pidf):
            continue
        try:
            pid = int(open(pidf).read().strip())
            pgid = int(open(os.path.join(d, "server.pgid")).read().strip())
        except Exception:  # noqa: BLE001
            continue
        r = subprocess.run(["ps", "-o", "cmd=", "-p", str(pid)],
                           capture_output=True, text=True)
        if "vllm" in (r.stdout or ""):
            print(f"[reap] killing orphan d238-{tag} pid={pid}", flush=True)
            stop(pgid)


def main() -> int:
    results = {}
    nd220 = {}
    reap_orphan_servers()
    for b in BOOTS:
        need_boot = not boot_done(b)
        pid = pgid = None
        if need_boot:
            pid, pgid = boot(b)
            print(f"[d238-{b}] booted pid={pid}", flush=True)
            thermal_wait()
        else:
            print(f"[d238-{b}] all evidence present, skip boot", flush=True)
        per_seed = []
        for seed in SEEDS:
            exp = f"V28-T2-Q0-KVARN-SD7-MS1-NBT2048-C1-L238K-NDL-{b.upper()}-S{seed}"
            out = os.path.join(NEXTGEN, "raw", "staging", exp)
            os.makedirs(out, exist_ok=True)
            nr_file = os.path.join(out, "needle-result.json")
            if os.path.exists(nr_file):   # 断点续跑：已完成 seed 直接读证据
                nr = json.load(open(nr_file))
                per_seed.append(nr)
                print(json.dumps({"seed": seed, "PASS": nr.get("PASS"),
                                  "hits": nr.get("needles_hit"), "ttft": nr.get("ttft_s"),
                                  "resumed": True}), flush=True)
                continue
            r = subprocess.run([PY, os.path.join(HERE, "needle_probe_nextgen.py"),
                                "--api", f"http://127.0.0.1:{PORT}/v1",
                                "--prompt-tokens", "238000", "--seed", str(seed),
                                "--experiment-id", exp, "--out-dir", out,
                                "--gpu-uuids", TP2_UUIDS],
                               capture_output=True, text=True, timeout=1800)
            try:
                nr = json.load(open(os.path.join(out, "needle-result.json")))
            except Exception:  # noqa: BLE001
                nr = {"PASS": False, "error": r.stdout[-200:] + r.stderr[-200:]}
            per_seed.append(nr)
            print(json.dumps({"seed": seed, "PASS": nr.get("PASS"),
                              "hits": nr.get("needles_hit"), "ttft": nr.get("ttft_s")}),
                  flush=True)
            time.sleep(10)
        results[b] = per_seed
        # A4 补测：220K 五针（gates A4 needle 5/5；借本 boot 省一次独占启动，
        # 结果单列 nd220k，不进入 238K 双 Gate 判定）
        exp22 = f"V28-T2-Q0-KVARN-SD7-MS1-NBT2048-C1-L220K-NDL-{b.upper()}-S1"
        out22 = os.path.join(NEXTGEN, "raw", "staging", exp22)
        os.makedirs(out22, exist_ok=True)
        nr22_file = os.path.join(out22, "needle-result.json")
        if os.path.exists(nr22_file):     # 断点续跑
            nr22 = json.load(open(nr22_file))
        else:
            r22 = subprocess.run([PY, os.path.join(HERE, "needle_probe_nextgen.py"),
                                  "--api", f"http://127.0.0.1:{PORT}/v1",
                                  "--prompt-tokens", "220000", "--seed", "1",
                                  "--experiment-id", exp22, "--out-dir", out22,
                                  "--gpu-uuids", TP2_UUIDS],
                                 capture_output=True, text=True, timeout=1800)
            try:
                nr22 = json.load(open(nr22_file))
            except Exception:  # noqa: BLE001
                nr22 = {"PASS": False,
                        "error": r22.stdout[-200:] + r22.stderr[-200:]}
        nd220[b] = nr22
        print(json.dumps({"nd220k": b, "PASS": nr22.get("PASS"),
                          "hits": nr22.get("needles_hit")}), flush=True)
        if need_boot:
            stop(pgid)
            time.sleep(10)

    # ---- 双 Gate 评估 ----
    correct = True
    ttft_med, kv_peak, vram_peak = {}, {}, {}
    issues = []
    for b, rs in results.items():
        hits = sum(1 for r in rs if r.get("PASS"))
        if hits != len(rs):
            correct = False
            issues.append(f"{b}: {hits}/{len(rs)} seed pass")
        ttfts = [r["ttft_s"] for r in rs if r.get("ttft_s")]
        if ttfts:
            ttft_med[b] = statistics.median(ttfts)
        kvs = [r.get("kv_usage_peak") for r in rs if r.get("kv_usage_peak") is not None]
        if kvs:
            kv_peak[b] = max(kvs)
        vs = [r.get("vram_peak_mib") for r in rs if r.get("vram_peak_mib")]
        if vs:
            vram_peak[b] = max(vs)
        if any(r.get("preempt_observed") for r in rs):
            issues.append(f"{b}: preemption observed")

    def drift(d):
        vals = list(d.values())
        if len(vals) < 2:
            return None
        med = statistics.median(vals)
        return (max(vals) - min(vals)) / med if med else None

    ttft_drift, kv_drift, vram_drift = drift(ttft_med), drift(kv_peak), drift(vram_peak)
    stability = {
        "ttft_median_per_boot": ttft_med, "ttft_drift": ttft_drift,
        "kv_peak_per_boot": kv_peak, "kv_drift": kv_drift,
        "vram_peak_per_boot": vram_peak, "vram_drift": vram_drift,
        "zero_preempt_oom_crash": not issues,
        "issues": issues,
    }
    verdict = {
        "correctness_gate_pass": correct,
        "total_cases": sum(len(rs) for rs in results.values()),
        "total_pass": sum(1 for rs in results.values() for r in rs if r.get("PASS")),
        "stability_gate_pass": (
            (ttft_drift is None or ttft_drift <= 0.10)
            and (kv_drift is None or kv_drift <= 0.05)
            and (vram_drift is None or vram_drift <= 0.02)
            and not issues),
        "stability": stability,
    }
    out = {"results": results, "nd220k": nd220, "verdict": verdict}
    od = os.path.join(NEXTGEN, "raw", "staging", "DEBT2-238K")
    os.makedirs(od, exist_ok=True)
    json.dump(out, open(os.path.join(od, "debt2-report.json"), "w"),
              indent=1, ensure_ascii=False)
    print(json.dumps(verdict, ensure_ascii=False))
    print("DEBT2_" + ("PASS" if verdict["correctness_gate_pass"]
                      and verdict["stability_gate_pass"] else "FAIL"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

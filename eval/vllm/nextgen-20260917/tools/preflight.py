#!/usr/bin/env python3
"""Preflight（Phase 00 §6.1 + v2.1 第 7/8/14 条）。

只读检查 + 僵尸三重凭据核验（核验后由人工/主流程执行 TERM）。
产出 repro/host-snapshot.json、env-lock.json、preflight-report.json。
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
sys.path.insert(0, HERE)
import nvml_bind  # noqa: E402
import host_snapshot  # noqa: E402

EXPECT = {  # MANIFEST.yaml gpu_identity_gate
    2: ("GPU-41a1986d-e745-9e40-c520-09490081fd44", "00000000:0E:00.0"),
    3: ("GPU-5fa853cd-219a-5d4e-dd1d-6d6d1f1390ae", "00000000:11:00.0"),
    4: ("GPU-aab40825-81bd-fb47-0bcf-a15cb19c2e7e", "00000000:16:00.0"),
}
FORBIDDEN_LOGICAL = (0, 1)


def sh(cmd: str) -> str:
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def check_gpu_identity(cards: list[dict]) -> dict:
    got = {c["logical_index"]: (c["uuid"], c["pci_bdf"].upper()) for c in cards}
    mismatches = {}
    for idx, (uuid, bdf) in EXPECT.items():
        g = got.get(idx)
        if g is None or g[0] != uuid or g[1] != bdf.upper():
            mismatches[idx] = {"expected": [uuid, bdf], "got": g}
    return {"ok": not mismatches, "mismatches": mismatches,
            "logical_to_uuid": {str(k): v[0] for k, v in got.items()}}


def check_clock() -> dict:
    sync = sh("timedatectl show -p NTPSynchronized -p NTP 2>/dev/null || true")
    offset = sh("grep -m1 'system time' /var/log/syslog 2>/dev/null || timedatectl 2>/dev/null | grep -i offset || true")
    return {"status": sync or "unavailable", "offset_hint": offset[:120] or "unknown"}


def check_cpu_governor() -> dict:
    g = sh("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null")
    return {"governor": g or "unknown"}


def zombie_evidence(pid: int) -> dict:
    """三重凭据：/proc cmdline + start time/user + 端口 socket owner。"""
    ev = {"pid": pid}
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            ev["cmdline"] = f.read().decode("utf-8", "replace").replace("\x00", " ")[:400]
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
        ev["starttime_ticks"] = parts[21]
        ev["state"] = parts[2]
    except FileNotFoundError:
        ev["gone"] = True
        return ev
    ev["user"] = sh(f"ps -o user= -p {pid}")
    owners = sh(f"ss -tlnp 2>/dev/null | grep ':{19649} ' || true")
    ev["port_19649_owner_line"] = owners[:300]
    ev["identity_match"] = ("vllm" in ev.get("cmdline", "")
                            and "19649" in ev.get("cmdline", "")
                            and str(pid) in owners)
    # 子进程僵尸状态
    children = sh(f"ps --ppid {pid} -o pid=,stat=,cmd= 2>/dev/null | head -5")
    ev["children"] = children
    return ev


def main() -> int:
    report: dict = {"captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # 0. stale staging 恢复扫描
    staging = os.path.join(NEXTGEN, "raw", "staging")
    stale = os.listdir(staging) if os.path.isdir(staging) else []
    report["stale_staging"] = stale

    # 1. GPU 身份 Gate
    cards = nvml_bind.snapshot_gpus()
    report["gpu_identity_gate"] = check_gpu_identity(cards)
    report["gpu_occupancy"] = [
        {"logical_index": c["logical_index"], "uuid": c["uuid"],
         "mem_used_mib": c["mem_used_mib"], "temp_c": c["temp_c"],
         "power_draw_w": c["power_draw_w"], "power_limit_w": c["power_limit_w"]}
        for c in cards]
    busy = [c for c in cards if c["mem_used_mib"] > 500]
    allowed_busy = [c for c in busy if c["logical_index"] in FORBIDDEN_LOGICAL]
    report["experiment_pool_free"] = not any(
        c["logical_index"] not in FORBIDDEN_LOGICAL for c in busy)

    # 2. 时钟/governor
    report["clock"] = check_clock()
    report["cpu"] = check_cpu_governor()

    # 3. host snapshot + env lock
    host = host_snapshot.collect_host()
    env = host_snapshot.collect_env_lock()
    hsp = os.path.join(NEXTGEN, "repro", "host-snapshot.json")
    elp = os.path.join(NEXTGEN, "repro", "env-lock.json")
    json.dump(host, open(hsp, "w"), indent=1, ensure_ascii=False)
    json.dump(env, open(elp, "w"), indent=1, ensure_ascii=False)
    import hashlib
    def sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    report["host_snapshot_sha256"] = sha(hsp)
    report["env_lock_sha256"] = sha(elp)

    # 4. 模型 SHA 抽查：参考清单中本 target 的行数 + 抽 1 个分片实算比对
    ref = os.path.join(os.path.dirname(NEXTGEN), "cuda13", "usable-concurrency-20260916",
                       "repro", "manifests", "model-sha256.txt")
    model_dir = "/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128"
    spot = {"reference_manifest": ref, "lines": 0, "spot_checks": []}
    if os.path.exists(ref):
        for ln in open(ref):
            parts = ln.split()
            if len(parts) >= 2:
                spot["lines"] += 1
                want = parts[0] if len(parts[0]) == 64 else None
                name = parts[-1]
                if want and "merged-bf16-w4g128" in name and len(spot["spot_checks"]) < 1:
                    local = os.path.join(model_dir, os.path.basename(name))
                    if os.path.exists(local):
                        h = hashlib.sha256()
                        with open(local, "rb") as f:
                            for blk in iter(lambda: f.read(1 << 20), b""):
                                h.update(blk)
                        spot["spot_checks"].append({
                            "file": os.path.basename(name), "expected": want,
                            "actual": h.hexdigest(), "match": h.hexdigest() == want})
    report["model_sha_check"] = spot

    # 5. 僵尸进程证据（不杀，只采集证据交主流程裁决）
    zpid = 292658
    report["zombie_evidence"] = zombie_evidence(zpid)

    # 6. 空闲温度基线（连续 3 次、间隔 2s；按逻辑卡号 2/3/4）
    temps = {str(k): [] for k in EXPECT}
    for _ in range(3):
        cs = nvml_bind.snapshot_gpus()
        cur = {c["logical_index"]: c["temp_c"] for c in cs}
        for k in EXPECT:
            temps[str(k)].append(cur.get(k))
        time.sleep(2)
    report["idle_temp_baseline_c"] = temps

    out = os.path.join(NEXTGEN, "repro", "preflight-report.json")
    json.dump(report, open(out, "w"), indent=1, ensure_ascii=False)
    gate_ok = report["gpu_identity_gate"]["ok"] and report["experiment_pool_free"]
    print(json.dumps({
        "preflight_report": out,
        "gpu_identity_gate": report["gpu_identity_gate"]["ok"],
        "experiment_pool_free": report["experiment_pool_free"],
        "stale_staging": stale,
        "zombie_identity_match": report["zombie_evidence"].get("identity_match"),
        "gate": "PASS" if gate_ok else "ENV_DRIFT_BLOCK",
    }, ensure_ascii=False))
    return 0 if gate_ok else 10


if __name__ == "__main__":
    sys.exit(main())

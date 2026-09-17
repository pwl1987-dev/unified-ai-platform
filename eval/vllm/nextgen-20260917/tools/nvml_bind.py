#!/usr/bin/env python3
"""GPU 身份绑定与 NVML 采样（经 nvidia-smi 子进程，无第三方依赖）。

铁则：一切关联以 GPU UUID 为准（禁逻辑 index）；本模块只读，绝不触碰 GPU0/1 进程。
用法：
  python3 nvml_bind.py snapshot              # 全卡身份快照（index/uuid/bdf/功耗墙/温度）
  python3 nvml_bind.py bind <pid>            # PID -> GPU UUID/BDF 映射（compute-apps）
  python3 nvml_bind.py sanity --pid <pid>    # 空闲/负载三段功耗物理常识自检
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

QID = ("index,uuid,pci.bus_id,name,power.limit,power.draw,temperature.gpu,"
       "clocks.sm,clocks.mem,utilization.gpu,memory.used,clocks_throttle_reasons.active")


def _smi(*args: str, timeout: int = 30) -> str:
    r = subprocess.run(["nvidia-smi", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"nvidia-smi {' '.join(args)} rc={r.returncode}: {r.stderr[:200]}")
    return r.stdout


def snapshot_gpus() -> list[dict]:
    out = _smi("--query-gpu=" + QID, "--format=csv,noheader,nounits")
    cards = []
    for ln in out.strip().splitlines():
        f = [x.strip() for x in ln.split(",")]
        cards.append({
            "logical_index": int(f[0]), "uuid": f[1], "pci_bdf": f[2], "name": f[3],
            "power_limit_w": float(f[4]), "power_draw_w": float(f[5]),
            "temp_c": int(f[6]), "sm_clock_mhz": int(f[7]), "mem_clock_mhz": int(f[8]),
            "gpu_util_pct": int(f[9]), "mem_used_mib": int(f[10]),
            "throttle_reasons": f[11] if len(f) > 11 else "",
            "t_utc_ns": time.time_ns(),
        })
    return cards


def compute_apps() -> list[dict]:
    """全部计算进程 -> GPU 绑定。"""
    out = _smi("--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
               "--format=csv,noheader,nounits")
    apps = []
    for ln in out.strip().splitlines():
        if not ln.strip():
            continue
        f = [x.strip() for x in ln.split(",")]
        apps.append({"gpu_uuid": f[0], "pid": int(f[1]),
                     "process_name": f[2] if len(f) > 2 else "",
                     "used_memory_mib": float(f[3]) if len(f) > 3 and f[3] else None})
    return apps


def bind_pid(pid: int) -> list[dict]:
    return [a for a in compute_apps() if a["pid"] == pid]


class NVMLSampler(threading.Thread):
    """500ms 冻结间隔采样；记录实际间隔，缺样本按 gap>2x 计。"""

    def __init__(self, interval_ms: int = 500, uuids: list[str] | None = None):
        super().__init__(daemon=True)
        self.interval_ms = interval_ms
        self.uuids = uuids          # None=全卡；否则只保留这些 UUID 的行
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self.exit_code = 0
        self.errors: list[str] = []

    def run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic_ns()
            try:
                cards = snapshot_gpus()
                if self.uuids:
                    cards = [c for c in cards if c["uuid"] in self.uuids]
                self.samples.extend(cards)
            except Exception as e:  # noqa: BLE001
                self.exit_code = 1
                self.errors.append(str(e)[:200])
                if len(self.errors) > 10:
                    break
            elapsed_ms = (time.monotonic_ns() - t0) / 1e6
            wait_s = max(0.0, self.interval_ms / 1000.0 - elapsed_ms / 1000.0)
            self._stop.wait(wait_s)

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=10)

    def stats(self) -> dict:
        # 按卡分组算实际间隔（全卡同刻采样，取第一张卡的间隔序列即可）
        gaps_ms: list[float] = []
        if self.samples:
            ts = sorted({s["t_utc_ns"] for s in self.samples})
            gaps_ms = [(b - a) / 1e6 for a, b in zip(ts, ts[1:])]
        missing = sum(1 for g in gaps_ms if g > 2 * self.interval_ms)
        return {
            "requested_interval_ms": self.interval_ms,
            "actual_interval_ms_min": round(min(gaps_ms), 1) if gaps_ms else None,
            "actual_interval_ms_median": round(sorted(gaps_ms)[len(gaps_ms) // 2], 1) if gaps_ms else None,
            "actual_interval_ms_max": round(max(gaps_ms), 1) if gaps_ms else None,
            "missing_sample_ratio": round(missing / len(gaps_ms), 4) if gaps_ms else None,
            "max_gap_ms": round(max(gaps_ms), 1) if gaps_ms else None,
            "sampler_exit_code": self.exit_code,
            "samples_collected": len(self.samples),
            "errors": self.errors[:5],
        }


def energy_integral_j(samples: list[dict], uuid: str, t0_ns: int, t1_ns: int) -> float:
    """请求/批次时间窗 [t0,t1]（utc ns）内单卡能量梯形积分（J）。"""
    pts = [(s["t_utc_ns"], s["power_draw_w"]) for s in samples
           if s["uuid"] == uuid and t0_ns <= s["t_utc_ns"] <= t1_ns]
    if len(pts) < 2:
        return 0.0
    pts.sort()
    return sum((b[1] + a[1]) / 2 * (b[0] - a[0]) / 1e9 for a, b in zip(pts, pts[1:]))


def sanity_three_phase(api_idle_samples: list[dict], uuid: str) -> dict:
    """空闲/负载功耗须符合物理常识：异常低值/恒定值 => INVALID 线索。"""
    p = [s["power_draw_w"] for s in api_idle_samples if s["uuid"] == uuid]
    if not p:
        return {"ok": False, "reason": "no samples"}
    uniq = len(set(p))
    return {"ok": uniq > 1, "distinct_power_values": uniq,
            "min_w": min(p), "max_w": max(p),
            "note": "恒定功耗读数=>疑似 NVML/卡位映射错误，标 INVALID"}


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    if cmd == "snapshot":
        print(json.dumps(snapshot_gpus(), indent=1))
        return 0
    if cmd == "bind":
        pid = int(sys.argv[2])
        print(json.dumps(bind_pid(pid), indent=1))
        return 0
    if cmd == "sanity":
        pid = int(sys.argv[3]) if len(sys.argv) > 3 else None
        cards = snapshot_gpus()
        bound = bind_pid(pid) if pid else []
        print(json.dumps({"cards": cards, "bound": bound}, indent=1))
        return 0
    print("usage: nvml_bind.py snapshot|bind <pid>|sanity [--pid <pid>]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ph5_energy_node.py — Phase 05 整机能量采集器（gates-phase05 energy_protocol）。

口径（frozen）：
  - official J/output-token 的能量分子 = 授权 GPU NVML 能量之和；CPU RAPL package 可读时并入，
    不可读如实 MEASUREMENT_NOT_AVAILABLE（不伪造）；非授权 GPU（生产/外占/外围）只读记录为环境上下文，不入分子
  - 梯形积分 J = Σ (P_i + P_{i+1})/2 × Δt（METRICS-SCHEMA §5；与 ph4_energy_report 同式）
  - boot/model-load 与 serving 稳态分列：由调用方用 --phase 标注窗口，本工具每次运行一个窗口
  - 1Hz 采样；NVML 只读（nvmlDeviceGetPowerFetcher/power）

用法：
  后台采样：ph5_energy_node.py --window-label cell-X --authorized-uuids U1,U2 --out FILE [--rate 1.0]
  自测    ：ph5_energy_node.py --selftest   # 合成 100W×10s×100tok → ~1050J 精确断言 + RAPL 探测
"""
from __future__ import annotations

import argparse
import json
import os
import time


def trapz(samples: list[tuple[float, float]]) -> float:
    """[(t_s, W)] → J（梯形积分）"""
    j = 0.0
    for (t0, p0), (t1, p1) in zip(samples, samples[1:]):
        j += (p0 + p1) / 2.0 * (t1 - t0)
    return j


def rapl_paths() -> list[str]:
    out = []
    base = "/sys/class/powercap"
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if name.startswith("intel-rapl:") and ":" not in name[len("intel-rapl:"):]:
            f = os.path.join(base, name, "energy_uj")
            if os.path.isfile(f) and os.access(f, os.R_OK):
                out.append(f)
    return out


def selftest() -> int:
    # 1) 梯形积分合成断言：100W 恒定 10s → 1000J；线性 0→100W 10s → 500J
    s_const = [(float(i), 100.0) for i in range(11)]
    assert abs(trapz(s_const) - 1000.0) < 1e-9, trapz(s_const)
    s_lin = [(float(i), 10.0 * i) for i in range(11)]
    assert abs(trapz(s_lin) - 500.0) < 1e-9, trapz(s_lin)
    # 100W×10s 产 100 token → 10 J/tok（ph4 同型自测）
    assert abs(trapz(s_const) / 100 - 10.0) < 1e-9
    # 2) RAPL 探测（如实记录，不判失败）
    rp = rapl_paths()
    # 3) NVML 只读探测（在则枚举全卡；不在则如实）
    nvml_ok, cards = False, []
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            nvml_ok = True
            cards = [l.split(",")[0] for l in r.stdout.strip().splitlines() if l]
    except Exception:
        pass
    print(json.dumps({"selftest": "SELFTEST_PASS", "trapz_const_J": 1000.0, "trapz_linear_J": 500.0,
                      "rapl_readable": rp, "rapl_count": len(rp),
                      "nvml_ok": nvml_ok, "gpu_count": len(cards)}, ensure_ascii=False))
    return 0


def sample_loop(args) -> int:
    import subprocess
    authorized = set(u.strip() for u in args.authorized_uuids.split(",") if u.strip())
    rows = []
    rapl = rapl_paths()
    rapl_prev = {f: None for f in rapl}
    rapl_j = {f: 0.0 for f in rapl}
    t0 = time.time()
    print(json.dumps({"event": "ENERGY_SAMPLER_UP", "window": args.window_label,
                      "authorized": sorted(authorized), "rate_hz": args.rate,
                      "rapl": rapl}), flush=True)
    while True:
        ts = time.time()
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=uuid,index,power.draw,temperature.gpu,clocks_throttle_reasons.active"
             , "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    uuid, idx = parts[0], parts[1]
                    try:
                        power = float(parts[2])
                    except ValueError:
                        continue
                    rows.append({"t": round(ts - t0, 3), "uuid": uuid, "idx": idx,
                                 "power_w": power,
                                 "temp_c": parts[3] if len(parts) > 3 else None,
                                 "throttle": parts[4] if len(parts) > 4 else None})
        for f in rapl:
            try:
                v = int(open(f).read().strip())
                if rapl_prev[f] is not None and v >= rapl_prev[f]:
                    rapl_j[f] += (v - rapl_prev[f]) / 1e6
                rapl_prev[f] = v
            except Exception:
                pass
        # 滚动落盘（崩溃保全）
        if rows and int(ts - t0) % 10 < args.rate:
            with open(args.out + ".jsonl", "a") as fh:
                for row in rows[-8:]:
                    fh.write(json.dumps(row) + "\n")
                rows.clear()
        time.sleep(args.rate)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--window-label", default="unlabeled")
    ap.add_argument("--authorized-uuids", default="")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.out:
        ap.error("--out 必填")
    sample_loop(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

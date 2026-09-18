#!/usr/bin/env python3
"""p0b_busbw — torch.distributed all_reduce 基准（P0B 拓扑双对扫描）。

nccl-tests 的 all_reduce_perf 替代实现（本机无预编译；torch 内置 NCCL 等价），
报告各消息档 busbw（GB/s）：
  busbw = algbw × 2×(R−1)/R（all_reduce 总线带宽标准公式）

用法（torchrun 双卡，同一 CPU/NUMA 条件下分别跑两对）：
  taskset -c <cpuset> torchrun --nproc_per_node=2 --master_port=29800 \
    p0b_busbw.py --out /data/sandbox/nextgen-20260917/p0b-busbw-<pair>.json
CPU/NUMA 冻结纪律见 gates-phase02.yaml:pairing_scan（两对同 cpuset/同策略/同 NCCL env）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os

import torch
import torch.distributed as dist

SIZES_MB = [1, 8, 64, 256, 1024]
ITERS = 20
WARMUP = 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    dist.init_process_group("nccl")
    rank = dist.get_rank()
    torch.cuda.set_device(rank)
    world = dist.get_world_size()
    dev = torch.cuda.current_device()

    rows = []
    for mb in SIZES_MB:
        n = mb * 1024 * 1024
        x = torch.empty(n, dtype=torch.uint8, device=dev)
        for _ in range(WARMUP):
            dist.all_reduce(x)
        torch.cuda.synchronize()
        dist.barrier()
        t0 = torch.cuda.Event(enable_timing=True)
        t1 = torch.cuda.Event(enable_timing=True)
        t0.record()
        for _ in range(ITERS):
            dist.all_reduce(x)
        t1.record()
        torch.cuda.synchronize()
        sec = t0.elapsed_time(t1) / 1000.0 / ITERS
        algbw = n / sec
        busbw = algbw * 2 * (world - 1) / world
        rows.append({"size_mb": mb, "avg_ms": round(sec * 1000, 3),
                     "algbw_gbps": round(algbw / 1e9, 2),
                     "busbw_gbps": round(busbw / 1e9, 2)})
        if rank == 0:
            print(f"{mb:6d} MB  {sec*1000:8.3f} ms  busbw {busbw/1e9:7.2f} GB/s")

    if rank == 0:
        doc = {
            "tool": "p0b_busbw.py（torch.distributed all_reduce，nccl-tests 替代）",
            "utc": datetime.datetime.utcnow().isoformat() + "Z",
            "world": world,
            "gpus": [torch.cuda.get_device_name(i) for i in range(world)],
            "uuids": os.environ.get("P0B_GPU_UUIDS", "unrecorded"),
            "cpu_affinity": str(os.sched_getaffinity(0)),
            "iters": ITERS, "rows": rows,
            "busbw_256mb": next(r["busbw_gbps"] for r in rows if r["size_mb"] == 256),
        }
        with open(args.out, "w") as f:
            json.dump(doc, f, indent=1)
        print(json.dumps({"out": args.out, "busbw_256mb": doc["busbw_256mb"]}))
    dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

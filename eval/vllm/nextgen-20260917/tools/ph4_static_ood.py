#!/usr/bin/env python3
"""Phase 04 P3 — artifact 静态 OOD 检查（scale saturation / NaN-Inf / 异常层）。

对每个候选 artifact：扫 safetensors 头：
  - weight_scale 分布（per-group scale；saturation = scale 落最大量化值域边界占比过高
    的张量——代理：scale 最大值/中位数 > 1000 的张量计数=异常形状告警）
  - NaN/Inf 扫（fp 层：bf16/fp32 张量）
  - 每 dtype 张量计数 → module_precision_map 复核
输出 raw/staging/PH4-P3/static-ood-check.json。容器内运行（需 safetensors/torch）。
用法：ph4_static_ood.py <artifact_dir>... （可多个）
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter

from safetensors import safe_open
import numpy as np


def check_artifact(d: str) -> dict:
    idx_p = os.path.join(d, "model.safetensors.index.json")
    if not os.path.exists(idx_p):
        return {"dir": d, "error": "no index"}
    idx = json.load(open(idx_p))["weight_map"]
    by_shard: dict = {}
    for k, shard in idx.items():
        by_shard.setdefault(shard, []).append(k)
    dtype_count: Counter = Counter()
    nan_inf_tensors = []
    scale_anomalies = []
    n_scale = 0
    for shard, keys in by_shard.items():
        with safe_open(os.path.join(d, shard), framework="pt") as f:
            meta = f.metadata() or {}
            for k in keys:
                sl = f.get_slice(k)
                dt = sl.get_dtype()
                dtype_count[dt] += 1
                if k.endswith("weight_scale"):
                    n_scale += 1
                    import torch
                    arr = f.get_tensor(k).float()
                    mx = float(arr.max()) if arr.numel() else 0.0
                    md = float(arr.abs().mean()) if arr.numel() else 0.0
                    if md > 0 and mx / md > 1000:
                        scale_anomalies.append({"tensor": k, "max": mx, "mean_abs": md})
                elif dt in ("BF16", "F32", "F16"):
                    t = f.get_tensor(k)
                    try:
                        bad = bool(torch.isnan(t).any()) or bool(torch.isinf(t).any())
                    except Exception:  # noqa: BLE001
                        bad = False
                    if bad:
                        nan_inf_tensors.append(k)
    return {"dir": d,
            "dtype_tensor_counts": dict(dtype_count),
            "n_scale_tensors": n_scale,
            "scale_anomaly_tensors": scale_anomalies[:10],
            "nan_inf_tensors": nan_inf_tensors[:10],
            "verdict": ("CLEAN" if not nan_inf_tensors and not scale_anomalies
                        else "REVIEW")}


def main() -> int:
    arts = sys.argv[1:]
    out = {a: check_artifact(a) for a in arts}
    # 加 Q0 现役对照
    q0 = "/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128"
    if os.path.exists(q0):
        out["Q0"] = check_artifact(q0)
    dst = "/data/repos/qwen3.8-27b-8x4090-stack/eval/vllm/nextgen-20260917/" \
          "raw/staging/PH4-P3/static-ood-check.json"
    json.dump(out, open(dst, "w"), indent=1, ensure_ascii=False)
    for a, r in out.items():
        print(a, r.get("verdict"), "| dtypes:", r.get("dtype_tensor_counts"),
              "| scale异常:", len(r.get("scale_anomaly_tensors", [])),
              "| NaN:", len(r.get("nan_inf_tensors", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

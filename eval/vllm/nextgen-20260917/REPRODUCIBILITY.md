# REPRODUCIBILITY — nextgen-20260917 从零复现指南

> 状态：Phase 00 施工中骨架。Phase 09 前补齐全部条目；每缺一项即文档门未过。

## 1. 前置硬件

- 4×RTX 4090 24GB（本战役锚点卡位见 `MANIFEST.yaml` `gpu_identity_gate`，含冻结 UUID+PCI BDF）
- 硬件校验：`python3 tools/host_snapshot.py --check repro/hardware-schema.json`（施工中）

## 2. 软件环境

- venv：`/data/tools/vllm28-env`（vLLM 0.28.0 / torch 2.13.0+cu130 / Python 3.12，**只读**）
- overlay：`/data/sandbox/vllm-cu130-qual-20260915/overlay-kvarn`（KVarN+DFlash2 补丁层，经 PYTHONPATH 挂载）
- 锁包与逐文件哈希：`eval/vllm/cuda13/usable-concurrency-20260916/repro/manifests/`
  - `vllm028-packages.lock.txt`、`model-sha256.txt`、`vllm028-kvarn-dflash2-w4a16.patch.sha256`
- 本机快照：`repro/host-snapshot.json` + `repro/env-lock.json`（preflight 生成，manifest 引用其 SHA256）

## 3. 模型放置

| 角色 | 路径约定 | 校验 |
|---|---|---|
| target | `/data/models/Qwen3.8-27B-coding-v1.1-W4A16-AutoRound/merged-bf16-w4g128` | model-sha256.txt |
| drafter | `/data/sandbox/vllm-cu130-qual-20260915/draft-recal-readable-20260915` | model-sha256.txt |

模型权重不入 Git；复现方按外部权重清单自行获取后跑 SHA256 校验。

## 4. 执行顺序

1. `python3 tools/preflight.py`（物理卡位 Gate + 环境/时钟/governor 检查）
2. `bash tools/boot028_nextgen.sh <tag> <port> [tp] [ms]`（缓存钉死 + PID/PGID 登记）
3. `python3 tools/bench_nextgen.py --api http://127.0.0.1:<port>/v1 ...`
4. `python3 tools/classify.py <experiment-id>`（schema 校验 + 六态归档）

## 5. 预期输出

- 每个 Gate 的参考值见 `repro/gates-phase00.yaml`；Phase 00 四锚点历史对照见 `reports/phase-00-baseline.md`（施工中）。

## 6. 允许差异与故障排查

- （Phase 09 前补：跨机容差、PCIe 降档、温度、NUMA 诊断阈值）

## 7. 脱敏检查

- 仓库内容不得含密钥/cookie/私密 prompt/不可迁移绝对路径（模型路径为机器约定，已在 §3 声明）。

## 8. 证据压缩变换（2026-09-17 commit #2 前）

- `raw/**/sampler-metrics.jsonl` 单文件 >2MB 者（30 个，原最大 106MB）已 `gzip -9`
  无损压缩为 `.jsonl.gz`（1.3G→126M；GitHub 单文件 100MB 硬限）。
  `gunzip -c <file>.gz` 可完整还原；采样统计摘要（interval/missing ratio/exit code）
  本就记录在各自 `metrics.json` 的 `sampler_stats`，不依赖原始序列。

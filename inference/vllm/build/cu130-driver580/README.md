# vLLM 0.28 原生 CUDA13 环境 · 驱动 580 时代（五坑配方）

> [返回项目首页](../../../../README.md) · [返回上级目录说明](../../README.md)

机器升驱动 580.173.02 + CUDA 13.0（2026-09-05 夜窗）后的原生 vLLM 环境，
实体验证于 `/data/tools/vllm28-env`（**vLLM 0.28.0 + torch 2.13.0+cu130 + transformers 5.16.1**，
2026-09-06 建，M 线推理统一底座）。uv 一键建：`uv venv && uv pip install "vllm[audio]==0.28.0"`。

## 启动模板（五坑全避）

```bash
V=/data/tools/vllm28-env; CUDA13=$V/lib/python3.12/site-packages/nvidia/cu13
CUDA_VISIBLE_DEVICES=N CUDA_HOME=$CUDA13 PATH=$CUDA13/bin:$V/bin:$PATH \
VLLM_USE_FLASHINFER_SAMPLER=0 CPATH=<python3.12 头路径> \
$V/bin/vllm serve <model> --port 801X ...
```

## 五坑（每个都实测踩过）

1. **CUDA_HOME 必须指 venv 内 `nvidia/cu13`**——0.28 wheel 自带完整 CUDA13 工具链（含 nvcc），系统无 toolkit；
2. **PATH 要含 `cu13/bin` 与 `venv/bin`**——flashinfer JIT 要 nvcc+ninja（`uv pip install ninja`）；
3. **`VLLM_USE_FLASHINFER_SAMPLER=0`**——否则 flashinfer 采样核 JIT 崩（自带 cccl 与 cu13 nvcc 版本冲突）；
4. **大视觉模型 OOM 三连**：`--max-num-batched-tokens 8192` + `--enforce-eager` + 改模型目录
   `video_preprocessor_config.json` 的 `longest_edge`（GLM 默认 1 亿像素 → 31457280≈32M）；
   27B 级视频模型双卡 TP2（单卡 KV 不够 45s 视频）；
5. **`pkill -f` 会自杀**——模式串匹配自家复合命令；用 pgrep 取 PID 再 kill，分两次执行。

## 与 27B 主力栈的关系

此环境用于 ASR/小型多模态服务化（Qwen3-ASR 原生 `/v1/audio/transcriptions`，45s 分片 bug 已修）。

**2026-09-15 27B 迁移实测更新**：同一现役 W4A16 checkpoint 在 stock 0.28 上因 INT8 embedding 的 `weight_packed` 无目标参数而加载失败；隔离 overlay 复用现有 `qwen3_5-embed-quant.patch` 逻辑后，target-only 已完整加载并 API Ready，p565/g512 三次中位 **57.95 tok/s**。同卡 0.27.1/cu129 target-only 为 57.685 tok/s，说明底座 decode 基本持平。

0.28 已原生包含 DFlash2。现役 recal W4A16 drafter 在 CUDA13 上只暴露两个额外兼容缺口：量化 qkv 的 context-K/V 需要 pack-quantized 解量化；candidate-selector 的 `flashinfer.top_k` JIT 会撞 CCCL/toolkit-header 冲突，资格 arm 用 `VLLM_DFLASH2_TORCH_TOPK=1` 强制 `torch.topk`。应用这两个最小 sandbox 修补后 32K text-only boot-1 API Ready，p565/g512 中位 **141.61 tok/s**，draft-token acceptance **32.08%**。补丁见本目录 `vllm028-dflash2-w4a16.patch`，原始数据与后续门见 `eval/vllm/cuda13/REPORT.md`。

**27B 生产主力仍保持 0.27.1-cu129 不动**；当前只进入 0.28/cu130 独立 fresh-boot 重复性门，尚未授权生产切换。

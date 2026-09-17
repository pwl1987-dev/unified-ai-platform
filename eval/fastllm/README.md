# FastLLM 替代资格评估——2026-09-15

> [返回项目首页](../../README.md) · [返回上级目录说明](../README.md)

范围：在 llama.cpp 生产线保持冻结的前提下，判断 FastLLM 是否能够替代 vLLM 高速通道。

## 稳定 Wheel 兼容性结果

隔离环境：`/data/sandbox/fastllm-qual-20260915/venv`，软件包 `ftllm==0.1.8.2`。

目标：与 vLLM 使用的生产目标相同，即 `Qwen3.8-27B-coding-v1.1-W4A16` AutoRound/compressed-tensors 检查点。

仅加载目标模型的 GPU4 冒烟测试在加载阶段失败，重复出现：

`FastLLM Error: SafeTensorItem.CreateBuffer: unsupport src dtype I32`

结论：**稳定版 `ftllm 0.1.8.2` 不能直接加载当前生产 W4A16 检查点**。这是检查点兼容性失败，不是性能或质量结论。终止测试后 GPU4 已恢复空闲，生产服务未被触碰。

## 当前源码线路

固定版本的上游 FastLLM 源码快照位于 `/data/sandbox/fastllm-qual-20260915/src`。

- FastLLM 提交：`74d36383312421e8316501aa46f7c002c8e490d9`
- pybind11 子模块提交：`0e2c3e5db41b6b2af4038734c84ab855ccaaa5f0`
- 构建目标：`fastllm_tools`，CUDA 12.9 构建容器，仅针对 RTX 4090 SM89
- 首次构建已进入 CUDA 编译阶段，唯一失败原因是运行时镜像缺少 `cublas_v2.h`；隔离恢复构建会补充 `cuda-libraries-dev-12-9`。

源码线路的兼容性仍为**待定**：必须先完成固定版本构建，再对同一个 W4A16 目标重新执行仅加载冒烟测试。

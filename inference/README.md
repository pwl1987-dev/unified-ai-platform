# inference/ · 推理运行时总览

> [返回项目首页](../README.md)

本目录提供 Qwen3.8-27B 的推理运行时、构建配方、负载均衡和可复现服务入口。

## 运行时导航

| 引擎 | 状态 | 入口 | 定位 |
|---|---|---|---|
| llama.cpp | ✅ 生产主力 | [`llamacpp/`](llamacpp/) | b10715、4 副本、256K、OpenResty/Lua LB |
| vLLM | 🧪 当前性能主线 | [`vllm/`](vllm/) | DFlash2、KVarN、长上下文、Coding Agent |
| SGLang | ⛔ 已归档 | [`sglang/`](sglang/) | 第三引擎探索、FP8 修复和回归原因 |

## 选择建议

- 需要稳定的多会话生产服务：使用 `llamacpp/`。
- 需要继续研究单卡高速、TP2 和长上下文：使用 `vllm/`，先阅读根目录测试总纲。
- 不要把 SGLang 当作当前替代方案；它的完整探索资料仍在 `sglang/`，包括结构化 tool_use 缺口和上下文容量修正。

## 构建与配套模块

| 模块 | 入口 | 说明 |
|---|---|---|
| llama.cpp CUDA 12.4 | [`llamacpp/build/cu124-driver550/`](llamacpp/build/cu124-driver550/) | 生产现役 b10715 构建配方 |
| llama.cpp 负载均衡 | [`llamacpp/lb/`](llamacpp/lb/) | 会话粘滞、大小会话分流和软摘除 |
| vLLM CUDA 12.9 | [`vllm/build/cu129-driver550/`](vllm/build/cu129-driver550/) | 0.27.1/cu129 生产镜像 |
| vLLM CUDA 13 | [`vllm/build/cu130-driver580/`](vllm/build/cu130-driver580/) | 0.28/cu130 原生迁移和五坑配方 |
| vLLM drafter | [`vllm/drafter/`](vllm/drafter/) | MTP、DFlash2 和 GPTQ 重校准 |
| vLLM KVarN | [`vllm/kvarn/`](vllm/kvarn/) | 4/2-bit KV cache backend 移植 |
| vLLM patches | [`vllm/patches/`](vllm/patches/) | 0.27.1 栈补丁清单 |

## 相关评测

- [推理线评测总览](../eval/README.md)
- [vLLM 下一代测试总纲](../eval/vllm/nextgen-20260917/MASTER-TEST-PLAN.md)
- [完整 vLLM 优化日志](../docs/VLLM-OPTIMIZATION.md)
- [问题与修复记录](../docs/PROBLEMS-AND-FIXES.md)

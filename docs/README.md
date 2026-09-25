# docs/ · 项目文档地图

> [返回项目首页](../README.md)

## 推荐阅读顺序

1. 先看根目录 [README](../README.md)，了解当前状态和入口。
2. 看 [总体功能设计](design/00-FUNCTIONAL-ARCHITECTURE.md)，了解模型无关、框架无关、厂商无关的 AI Compute & Model Engineering Platform 完整功能蓝图；当前 Qwen3.8 × 8×RTX4090 只是第一套真实参考工作负载。
3. 看 [技术栈基线](design/01-TECHNOLOGY-STACK.md)，了解 React/TypeScript + Go + Python 的前后端分工、数据层、事件总线与部署边界。
4. 再看 [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md)，了解已完成的优化实验。
5. 需要了解模型、量化和三引擎决策时，阅读 [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md)。
6. 需要继续推进时，阅读 [ROADMAP.md](ROADMAP.md) 和下一代 [MASTER-TEST-PLAN.md](../eval/vllm/nextgen-20260917/MASTER-TEST-PLAN.md)。

## 文档索引

| 文档 | 定位 |
|---|---|
| [design/00-FUNCTIONAL-ARCHITECTURE.md](design/00-FUNCTIONAL-ARCHITECTURE.md) | 模型/框架/厂商无关的 AI Compute & Model Engineering Platform 总体功能设计：统一网关、模型/数据/实验、GPU 调度、Agent 自动化、研究复现与成果转化 |
| [design/01-TECHNOLOGY-STACK.md](design/01-TECHNOLOGY-STACK.md) | 技术栈已冻结 v1.0：React/TypeScript 前端、Go Control Plane、Python AI/ML Worker、VM/Container 层、PostgreSQL/S3/NATS 与 Adapter-first 边界 |
| [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md) | 权重解剖、量化配方、MTP 实测、三引擎横评与 SGLang 决策 |
| [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md) | vLLM 生产线实验日志、DFlash2、KV、显存与 P0 归因 |
| [VLLM-OPTIMIZATION-PLAN-ARCHIVE.md](VLLM-OPTIMIZATION-PLAN-ARCHIVE.md) | 早期规划存档，不替代当前测试总纲 |
| [PROBLEMS-AND-FIXES.md](PROBLEMS-AND-FIXES.md) | 问题、踩坑、根因和修复记录 |
| [ROADMAP.md](ROADMAP.md) | 后续优化路线和待验证事项 |

## 规则

报告是解释层，`eval/**/raw/` 是证据层；阅读结论时必须同时检查对应原始数据和 commit SHA。

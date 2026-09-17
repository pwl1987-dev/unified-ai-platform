# docs/ · 项目文档地图

> [返回项目首页](../README.md)

## 推荐阅读顺序

1. 先看根目录 [README](../README.md)，了解当前状态和入口。
2. 再看 [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md)，了解已完成的优化实验。
3. 需要了解模型、量化和三引擎决策时，阅读 [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md)。
4. 需要继续推进时，阅读 [ROADMAP.md](ROADMAP.md) 和下一代 [MASTER-TEST-PLAN.md](../eval/vllm/nextgen-20260917/MASTER-TEST-PLAN.md)。

## 文档索引

| 文档 | 定位 |
|---|---|
| [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md) | 权重解剖、量化配方、MTP 实测、三引擎横评与 SGLang 决策 |
| [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md) | vLLM 生产线实验日志、DFlash2、KV、显存与 P0 归因 |
| [VLLM-OPTIMIZATION-PLAN-ARCHIVE.md](VLLM-OPTIMIZATION-PLAN-ARCHIVE.md) | 早期规划存档，不替代当前测试总纲 |
| [PROBLEMS-AND-FIXES.md](PROBLEMS-AND-FIXES.md) | 问题、踩坑、根因和修复记录 |
| [ROADMAP.md](ROADMAP.md) | 后续优化路线和待验证事项 |

## 规则

报告是解释层，`eval/**/raw/` 是证据层；阅读结论时必须同时检查对应原始数据和 commit SHA。

# eval/ · 评测与质量门禁

> [返回项目首页](../README.md)

评测目录按推理引擎分线，所有结论都必须能回溯到固定模型、fixture、环境、补丁、原始数据和重复规则。

## 评测导航

| 线路 | 状态 | 入口 | 重点 |
|---|---|---|---|
| llama.cpp | ✅ 已认证基线 | [`llamacpp/`](llamacpp/) | A/B 门禁、语义 Gate、RFT、rulers |
| vLLM | 🧪 当前主线 | [`vllm/`](vllm/) | P0、drafter、质量 A/B、长上下文、CUDA 13 |
| FastLLM | ⛔ 已归档 | [`fastllm/`](fastllm/) | 替代性资格、兼容性和负结果 |

## 统一判定原则

**“比现在好”必须可证伪**：全轴不低于基线，代码／工具核心轴严格提升；任一轴回退超过 2pp 即 FAIL。性能差异小于 3% 默认视为噪声，但质量、安全、OOM 和崩溃直接判定。

## 证据层级

- `raw/`：原始 JSON、JSONL、stdout、环境和探针结果，具有最高证据权重。
- `REPORT.md`：对实验形制、数据和结论的解释，不替代原始证据。
- `INVALID`、`UNSUPPORTED`、`REJECTED`：必须保留，不能只提交成功结果。
- 不同夹具、不同输出长度和不同拓扑不得直接计算加速比。

## 当前下一代评测

vLLM 0.29 + TP2 的执行入口为 [`vllm/nextgen-20260917/MASTER-TEST-PLAN.md`](vllm/nextgen-20260917/MASTER-TEST-PLAN.md)。顺序为：夹具修正 → 0.28 锚点 → 0.29 target-only → DFlash2 → KVarN → TP2／量化／拓扑 → 真实 Agent → 长稳 → 跨设备复现。

## 返回

- [推理运行时总览](../inference/README.md)
- [深度分析与优化文档](../docs/README.md)

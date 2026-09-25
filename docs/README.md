# docs/ · 项目文档地图

> [返回项目首页](../README.md)

## 推荐阅读顺序

1. 先看根目录 [README](../README.md)，了解当前状态和入口。
2. 看 [总体功能设计](design/00-FUNCTIONAL-ARCHITECTURE.md)，了解模型无关、框架无关、厂商无关的 AI Compute & Model Engineering Platform 完整功能蓝图；当前 Qwen3.8 × 8×RTX4090 只是第一套真实参考工作负载。
3. 看 [技术栈基线](design/01-TECHNOLOGY-STACK.md)，了解 React/TypeScript + Go + Python 的前后端分工、数据层、事件总线与部署边界。
4. 看 [任务分解基线](design/02-WORK-BREAKDOWN.md)，了解 P0-P10、七条并行轨道、UI/UX 时间点和第一批 Work Package。
5. 看 [Reuse / Build Matrix](design/03-REUSE-BUILD-MATRIX.md)，了解第三方能力哪些 REUSE / ADAPTER / BUILD / REPLACE_LATER / RESTRICTED，以及每项的 Authority、数据归属和 Exit Path。
6. 看 [User Roles](ux/01-ROLES.md)，了解首批九类产品角色、人机责任边界和后续 Golden Journey / IA / Low-fi 的设计输入。
7. 再看 [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md)，了解已完成的优化实验。
8. 需要了解模型、量化和三引擎决策时，阅读 [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md)。
9. 需要继续推进参考工作负载时，阅读 [ROADMAP.md](ROADMAP.md) 和下一代 [MASTER-TEST-PLAN.md](../eval/vllm/nextgen-20260917/MASTER-TEST-PLAN.md)。

## 文档索引

| 文档 | 定位 |
|---|---|
| [design/00-FUNCTIONAL-ARCHITECTURE.md](design/00-FUNCTIONAL-ARCHITECTURE.md) | 模型/框架/厂商无关的 AI Compute & Model Engineering Platform 总体功能设计：统一网关、模型/数据/实验、GPU 调度、Agent 自动化、研究复现与成果转化 |
| [design/01-TECHNOLOGY-STACK.md](design/01-TECHNOLOGY-STACK.md) | 技术栈已冻结 v1.0：React/TypeScript 前端、Go Control Plane、Python AI/ML Worker、VM/Container 层、PostgreSQL/S3/NATS 与 Adapter-first 边界 |
| [design/02-WORK-BREAKDOWN.md](design/02-WORK-BREAKDOWN.md) | P0-P10 任务分解基线：Reuse/Build、Domain/API、UI/UX、Foundation、Infra、Integration、AI Factory、Scheduler/Agent、Hardening 与 Release |
| [design/03-REUSE-BUILD-MATRIX.md](design/03-REUSE-BUILD-MATRIX.md) | WP-P0-01：19 类候选的 Reuse/Build 主判定、八问、License 风险、Authority 边界、Exit Path 与自主替代优先级 |
| [ux/01-ROLES.md](ux/01-ROLES.md) | WP-P2-01：Platform Admin、AI Engineer、Data/Knowledge Engineer、Researcher、App Developer、SRE、Security/Auditor、Approver、Viewer 九类角色与 AI Operator 边界 |
| [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md) | 权重解剖、量化配方、MTP 实测、三引擎横评与 SGLang 决策 |
| [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md) | vLLM 生产线实验日志、DFlash2、KV、显存与 P0 归因 |
| [VLLM-OPTIMIZATION-PLAN-ARCHIVE.md](VLLM-OPTIMIZATION-PLAN-ARCHIVE.md) | 早期规划存档，不替代当前测试总纲 |
| [PROBLEMS-AND-FIXES.md](PROBLEMS-AND-FIXES.md) | 问题、踩坑、根因和修复记录 |
| [ROADMAP.md](ROADMAP.md) | 后续优化路线和待验证事项 |

## 当前平台设计推进点

```text
Frozen Authority
  00 Functional Architecture
  01 Technology Stack
        ↓
Work Breakdown
  02 WBS
        ↓
First-pass Work Packages
  03 Reuse / Build Matrix
  ux/01 User Roles
        ↓
Next
  P1 Core Domain Model
  P2 Human-AI Responsibility
  P2 Golden Journeys
  P2 Information Architecture
  P2 Low-fi Wireframes
```

## 规则

报告是解释层，`eval/**/raw/` 是证据层；阅读结论时必须同时检查对应原始数据和 commit SHA。

平台设计文档额外遵守：

- Frozen Architecture / Technology Stack 只由有 Evidence 的 Architecture Change 修改；
- UI 只绑定我方 Domain Model / Control Hub API，不绑定第三方内部 DTO；
- 第三方复用必须经过 Adapter / Contract；
- Work Package 必须有明确 Acceptance Criteria 与 Exit Path。

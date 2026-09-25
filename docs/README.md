# docs/ · 项目文档地图

> [返回项目首页](../README.md)

## 推荐阅读顺序

1. 先看根目录 [README](../README.md)，了解当前状态和入口。
2. 看 [总体功能设计](design/00-FUNCTIONAL-ARCHITECTURE.md)，了解模型无关、框架无关、厂商无关的 AI Compute & Model Engineering Platform 完整功能蓝图；当前 Qwen3.8 × 8×RTX4090 只是第一套真实参考工作负载。
3. 看 [技术栈基线](design/01-TECHNOLOGY-STACK.md)，了解 React/TypeScript + Go + Python 的前后端分工、数据层、事件总线与部署边界。
4. 看 [任务分解基线](design/02-WORK-BREAKDOWN.md)，了解 P0-P10、七条并行轨道、UI/UX 时间点和第一批 Work Package。
5. 看 [Reuse / Build Matrix](design/03-REUSE-BUILD-MATRIX.md)，了解第三方能力哪些 REUSE / ADAPTER / BUILD / REPLACE_LATER / RESTRICTED，以及每项的 Authority、数据归属和 Exit Path。
6. 看 [Dependency Register](design/04-DEPENDENCY-REGISTER.md)，核对第三方 exact repo / audit revision / License Evidence / mirror / replacement path。
7. 看 [Core Domain Model](design/10-DOMAIN-MODEL.md)，了解核心 Domain Object、Stable ID、lifecycle、ownership、lineage、Evidence 和第三方 DTO 边界。
8. 看 [Northbound API Boundary](design/11-API-BOUNDARY.md) 与 [P1 Decision Register](design/12-DECISION-REGISTER.md)，了解 /v1、/api/v1、Capability-first API、统一错误/异步/审批/Gate contract 与 P1-D01~D06 裁决。
9. 看 [User Roles](ux/01-ROLES.md)，了解首批九类产品角色。
10. 看 [Human-AI Responsibility Matrix](ux/04-HUMAN-AI-RESPONSIBILITY.md)，了解 AI 可执行/仅建议/需人审/人类最终决定的边界。
11. 看 [Golden Journeys](ux/02-GOLDEN-JOURNEYS.md)，了解十条端到端任务流、Contract Gap 与 Orphan API Risk 审计。
12. 看 [Information Architecture](ux/03-INFORMATION-ARCHITECTURE.md)，了解八个一级导航、全局入口与对象跨域规则。
13. 看 [Low-fi Wireframes](ux/05-LOW-FI-WIREFRAMES.md)，了解 12 个核心页面的任务流、Authority、Evidence/Gate/Approval 和异常状态。
14. 再看 [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md)，了解 Reference Workload 已完成的优化实验。
15. 需要了解模型、量化和三引擎决策时，阅读 [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md)。
16. 需要继续推进参考工作负载时，阅读 [ROADMAP.md](ROADMAP.md) 和下一代 [MASTER-TEST-PLAN.md](../eval/vllm/nextgen-20260917/MASTER-TEST-PLAN.md)。

## 文档索引

| 文档 | 定位 |
|---|---|
| [design/00-FUNCTIONAL-ARCHITECTURE.md](design/00-FUNCTIONAL-ARCHITECTURE.md) | Functional Architecture Frozen v1.0；模型/框架/厂商无关的 Unified AI Gateway + AI Control Hub 总体功能设计 |
| [design/01-TECHNOLOGY-STACK.md](design/01-TECHNOLOGY-STACK.md) | Technology Stack Frozen v1.0；React/TypeScript、Go、Python、VM/Container、PostgreSQL/S3/NATS 与 Adapter-first 边界 |
| [design/02-WORK-BREAKDOWN.md](design/02-WORK-BREAKDOWN.md) | P0-P10 任务分解基线、七条并行轨道、UI/UX 时间点和 Work Package |
| [design/03-REUSE-BUILD-MATRIX.md](design/03-REUSE-BUILD-MATRIX.md) | WP-P0-01：19 类候选的 Reuse/Build 主判定、八问、Authority、Exit Path 与自主替代优先级 |
| [design/04-DEPENDENCY-REGISTER.md](design/04-DEPENDENCY-REGISTER.md) | WP-P0-02：第三方 audit revision、License Evidence、风险、内部镜像与 Replacement Register |
| [design/10-DOMAIN-MODEL.md](design/10-DOMAIN-MODEL.md) | WP-P1-01 + P1-D05 amendment：27 个核心对象 + Project/Principal 基础对象、Stable ID、spec/status、ownership、lineage 与 Evidence |
| [design/11-API-BOUNDARY.md](design/11-API-BOUNDARY.md) | WP-P1-02：Northbound API Boundary；/v1 AI Data Plane、/api/v1 Control/Governance Plane、async/error/evidence/approval/gate/mutation contract |
| [design/12-DECISION-REGISTER.md](design/12-DECISION-REGISTER.md) | P1-D01~D06 正式 Decision Register |
| [design/13-EVENT-CONTRACT.md](design/13-EVENT-CONTRACT.md) | WP-P1-03：Domain Event Envelope、事件族、at-least-once/idempotency、outbox/replay 与 Agent/Audit/Incident 事件 |
| [../contracts/events/event-envelope.schema.json](../contracts/events/event-envelope.schema.json) | WP-P1-03 machine-readable Event Envelope JSON Schema |
| [../contracts/events/event-catalog.v1.json](../contracts/events/event-catalog.v1.json) | WP-P1-03 machine-readable Event Catalog |
| [../contracts/openapi/unified-ai-platform.v1.json](../contracts/openapi/unified-ai-platform.v1.json) | OpenAPI 3.1 machine-readable baseline；用于 TypeScript/Go/Python client generation |
| [../contracts/schemas/domain-envelope.schema.json](../contracts/schemas/domain-envelope.schema.json) | WP-P1-01 机器可读 common Domain Envelope JSON Schema baseline |
| [ux/01-ROLES.md](ux/01-ROLES.md) | WP-P2-01：九类 User Roles 与 AI Operator 权限继承边界 |
| [ux/02-GOLDEN-JOURNEYS.md](ux/02-GOLDEN-JOURNEYS.md) | WP-P2-03：十条 Golden Journeys、R0-R3、Evidence/Gate/Approval、15 项 Contract Gap 与 Orphan API Risk 审计 |
| [ux/03-INFORMATION-ARCHITECTURE.md](ux/03-INFORMATION-ARCHITECTURE.md) | WP-P2-04：Home / AI Hub / Build / Run / Improve / Knowledge / Compute / Govern 与五个全局入口 |
| [ux/05-LOW-FI-WIREFRAMES.md](ux/05-LOW-FI-WIREFRAMES.md) | WP-P2-05：12 个核心页 Low-fi、Candidate/Production/LKG、spec/status、Evidence/Gate/Approval、AI suggestion/execution 与异常状态 |
| [ux/04-HUMAN-AI-RESPONSIBILITY.md](ux/04-HUMAN-AI-RESPONSIBILITY.md) | WP-P2-02：R0-R3 Human-AI Responsibility、预授权自动化、Decision Packet 和高风险动作边界 |
| [QWEN27B-ANALYSIS.md](QWEN27B-ANALYSIS.md) | 权重解剖、量化配方、MTP 实测、三引擎横评与 SGLang 决策 |
| [VLLM-OPTIMIZATION.md](VLLM-OPTIMIZATION.md) | vLLM 生产线实验日志、DFlash2、KV、显存与 P0 归因 |
| [VLLM-OPTIMIZATION-PLAN-ARCHIVE.md](VLLM-OPTIMIZATION-PLAN-ARCHIVE.md) | 早期规划存档，不替代当前测试总纲 |
| [PROBLEMS-AND-FIXES.md](PROBLEMS-AND-FIXES.md) | 问题、踩坑、根因和修复记录 |
| [ROADMAP.md](ROADMAP.md) | Reference Workload 后续优化路线和待验证事项 |

## 当前平台设计推进点

```text
Frozen Authority
  00 Functional Architecture
  01 Technology Stack
        ↓
Work Breakdown
  02 WBS
        ↓
Completed first-pass packages
  P0-01 Reuse / Build Matrix
  P0-02 Dependency Register
  P1-01 Core Domain Model
  P1-02 Northbound API Contract
  P1-03 Event Contract
  P2-01 User Roles
  P2-02 Human-AI Responsibility
  P2-03 Golden Journeys
  P2-04 Information Architecture
        ↓
Next Contract / UX layer
  P1-04 State Machines
  P1-05 Adapter Contract

  P2-05 Low-fi Wireframes
```

## 当前 P1 裁决登记

P1-D01~D06 已在 [design/12-DECISION-REGISTER.md](design/12-DECISION-REGISTER.md) 正式收敛。

关键结果：OCIRegistryAdapter；AssetSourceAdapter / AssetHubAdapter 拆分；ProviderAdapter / ServingAdapter 分离；Index 为 derivative；Project / Principal 一等化；business revision 与 resource_version 分离。

## 规则

报告是解释层，`eval/**/raw/` 是证据层；阅读结论时必须同时检查对应原始数据和 commit SHA。

平台设计文档额外遵守：

- Frozen Architecture / Technology Stack 只由有 Evidence 的 Architecture Change 修改；
- UI 只绑定我方 Domain Model / Control Hub API，不绑定第三方内部 DTO；
- 第三方复用必须经过 Adapter / Contract；
- Work Package 必须有明确 Acceptance Criteria 与 Exit Path；
- AI/Agent 不得通过 AI Operator、Command Palette 或 backend admin API 绕过同一套 Policy / Approval / Evidence。

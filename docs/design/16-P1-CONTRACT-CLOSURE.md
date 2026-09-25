# P1 Contract Closure v1.0

> Work Package：**WP-P1-CLOSE-01 / Golden Journey Contract Closure**
>
> 状态：**COMPLETE**
>
> 生效基线：OpenAPI 3.1 `info.version = 0.2.0`
>
> 目标：在不扩成“数百个 CRUD endpoint”的前提下，关闭 WP-P2-03 暴露的 15 个 Contract Gap，使 P2 Low-fi 的核心动作都有正式 Contract Owner。

# 1. Closure 原则

只补三类 surface：

1. Golden Journey 必需的显式 Action；
2. 第一轮核心详情页必需的 Read Model；
3. Approval / Incident / Migration 等跨域决策上下文。

仍不做：

- 全对象 CRUD；
- vendor passthrough；
- raw admin API；
- secret reveal；
- UI-only endpoint；
- Phase 06 专用 endpoint。

# 2. 新增 Northbound Surface

OpenAPI 从 15 个 operation 增补到当前 closure baseline。

新增核心 family：

- ModelAsset import + detail read；
- DatasetAsset import + detail read；
- Experiment create + detail read；
- KnowledgeAsset detail + Index rebuild；
- TrainingRun checkpoint/resume；
- Policy detail + optimistic-concurrency mutation；
- UpstreamDependency list/detail + begin migration；
- Adapter detail + backend replacement；
- ExternalRef migration mapping read；
- Approval request + Decision Packet read；
- Deployment detail + recover-to-LKG；
- Incident/recovery read projection。

# 3. CG-01~CG-15 最终状态

| Gap | Final status | Closing Contract |
|---|---|---|
| CG-01 ModelAsset intake | **CLOSED** | POST /api/v1/model-assets:import + AssetSource/AssetHub Adapter |
| CG-02 Dataset intake/revision | **CLOSED** | POST /api/v1/dataset-assets:import + revision semantics |
| CG-03 checkpoint/resume | **CLOSED** | Run checkpoint/resume API + TrainingRun SM + TrainingAdapter |
| CG-04 Experiment/Reproduction create | **CLOSED** | POST /api/v1/experiments |
| CG-05 Dependency snapshot/read | **CLOSED** | UpstreamDependency list/detail + dependency events |
| CG-06 Knowledge/Index rebuild | **CLOSED** | Knowledge detail + :rebuild-index + Vector/Search Adapter |
| CG-07 Scheduler Policy read/mutate | **CLOSED** | Policy GET/PATCH + P1-04 responsibility/guard |
| CG-08 preemption/resume orchestration | **CLOSED** | TrainingRun SM + checkpoint/resume API；preemption remains internal scheduler action |
| CG-09 Backend replacement | **CLOSED** | Adapter Contract + :replace-backend |
| CG-10 ExternalRef migration mapping | **CLOSED** | migration mapping read model |
| CG-11 Dependency risk/status | **CLOSED** | UpstreamDependency status read + risk state machine |
| CG-12 time-bounded governance exception | **CLOSED** | generic Approval request + DecisionPacket.exception_scope / expiry；不新增第二 PolicyException Authority |
| CG-13 Agent execution context / Decision Packet | **CLOSED** | DecisionPacket + ExecutionContextSummary + Approval GET；Agent 仍使用相同 Northbound API |
| CG-14 recover-to-LKG | **CLOSED** | POST Deployment :recover + Deployment SM + Serving rollback primitive |
| CG-15 incident/recovery read model | **CLOSED** | GET /api/v1/incidents/{incident_id} read-only projection |

# 4. 关键裁决

## 4.1 不新增 PolicyException 一级对象

License/Security/Policy exception 使用：

~~~text
Approval
+ Decision Packet
+ scope
+ expiry
+ Policy reference
~~~

风险对象本身仍保持 AT_RISK/BLOCKED 等真实状态。

这样避免“有 exception 就把风险改绿”。

## 4.2 Incident 是 read-only projection

第一阶段不把 Incident 新增为一等 Domain Object。

IncidentReadModel 聚合：

- affected Deployment/Capability；
- Event；
- Operation；
- Evidence；
- LKG；
- recovery status。

真实 mutation 仍回 Deployment / Operation / Policy。

如果未来需要 incident ownership/SLA/postmortem lifecycle，再通过 P1 Decision Register 升格。

## 4.3 Scheduler preemption 不暴露为通用手工 API

P1-04 已冻结 preemption state semantics。

外部用户可 checkpoint/resume；真正 preemption 由 Scheduler 在 Policy 内执行，避免 UI/Agent 直接抢占任意 workload 形成第二 Scheduler。

## 4.4 AI Operator 不新增超级 API

CG-13 通过 ExecutionContext + DecisionPacket + Approval read 闭合。

AI Operator：

- 不获得 /ai-admin/*；
- 不获得 bypass token；
- 不获得 backend admin endpoint；
- 所有副作用动作仍调用同一 Northbound Contract。

# 5. P2-05 Contract Pending Resolution

Low-fi 中曾标记 Contract Pending 的第一批动作现已有 Owner：

- Model/Dataset intake；
- Experiment reproduction create；
- Scheduler Policy mutation；
- checkpoint/resume；
- backend replacement；
- dependency risk exception；
- Agent Decision Packet；
- recover-to-LKG。

因此：

> P2-05 的任务流不再存在“无 Contract Owner 的核心按钮”。

实现阶段仍需按 operationId / generated client，不得手写 vendor request。

# 6. Orphan API Re-audit

新增 surface 均被 Golden Journey 或 12 个核心 Low-fi 页面直接消费。

- Model/Dataset detail → Model Detail / Dataset Detail；
- Experiment → Experiment/Benchmark；
- Knowledge → Knowledge；
- Policy/Dependency/Adapter/Approval → Govern / Approval Inbox；
- Deployment recover / Incident → Deployment / Home Attention；
- checkpoint/resume → Training Run；
- migration mapping → Backend Replacement Journey。

**Orphan API Risk：NONE at P1 closure baseline。**

# 7. P3 Readiness Decision

## P3-01 Repository Skeleton

**GO。**

理由：

- Functional Architecture frozen；
- Technology Stack frozen；
- Domain/API/Event/State/Adapter first-pass contract complete；
- Golden Journeys/IA/Low-fi complete；
- Contract Gap owner 已清零。

允许建立：

~~~text
apps/web
services/control-hub
services/gateway
workers/
adapters/
contracts/
deploy/
~~~

但本设计窗口不立即开始大规模业务编码。

## P3-02 Go Control Hub Bootstrap

**GO after P3-01**，仅 bootstrap 基础能力；不提前实现未验收的复杂业务 controller。

## P3-03 React App Bootstrap

**GO for shell/contract client only**。

真实视觉页面实现继续等待 P2-06 Design System Direction / P2-07 Hi-fi。

## P3-04 Python Worker SDK

**GO after P3-01**，以 Event/Adapter/Evidence contract 为输入。

## P3-05 Contract CI

**HIGH PRIORITY / should be first guard**。

至少验证：

- OpenAPI parse/ref；
- JSON Schema parse；
- operationId uniqueness；
- TypeScript / Go / Python generation smoke；
- Event catalog/schema；
- State machine schema/data；
- Adapter manifest/catalog；
- backward compatibility。

# 8. 下一设计任务裁决

Contract 主线已达到正式编码前第一轮收敛。

本窗口下一项应进入：

**WP-P2-06 Design System Direction**

原因：

- Low-fi 已稳定；
- API Boundary 已稳定到 Journey closure；
- P2-06 现在不会反向发明 Domain/API；
- P3 Repository Skeleton 可由编码线并行启动，但不应阻塞 UX 视觉系统收敛。

# 9. Acceptance Criteria

- [x] CG-01~CG-15 全部有 Contract Owner。
- [x] 未引入全量 CRUD。
- [x] 未引入 AI 超级 API。
- [x] 未引入 second Scheduler。
- [x] Incident 暂保持 read projection，不擅自新增一级对象。
- [x] governance exception 保持 Approval/Policy 语义。
- [x] OpenAPI additive extension 保持 /v1 与 /api/v1 boundary。
- [x] Backend replacement 不改变 stable Domain ID。
- [x] Low-fi 核心按钮不再无 Contract Owner。
- [x] P3-01 readiness 给出显式 GO。

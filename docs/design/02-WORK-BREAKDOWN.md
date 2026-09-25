
# Platform Work Breakdown Structure v0.1

> 状态：**任务分解基线（Work Breakdown Baseline）**
>
> 上位 Authority：
> - docs/design/00-FUNCTIONAL-ARCHITECTURE.md
> - docs/design/01-TECHNOLOGY-STACK.md
>
> 原则：先拆清边界，再写代码；UI/UX 与 Domain/API 并行，不作为开发末尾的“美化任务”。

---

# 1. 任务分解方法

所有工作按以下层级管理：

~~~text
Program
  ↓
Phase
  ↓
Workstream
  ↓
Work Package
  ↓
Task
  ↓
Acceptance Evidence
~~~

每个 Work Package 必须包含：

- Goal；
- Scope；
- Inputs；
- Outputs；
- Dependencies；
- Acceptance Criteria；
- Evidence；
- Owner Role；
- Gate；
- Exit Condition。

禁止出现只有“开发 XXX”“完善 XXX”但没有验收条件的任务。

---

# 2. 总体阶段

当前平台后续实施拆成 10 个阶段。

~~~text
P0  Reuse / Build Decision
P1  Domain Model & Contract
P2  UX / IA / Low-fi Prototype
P3  Foundation Skeleton
P4  Infrastructure & Runtime Foundation
P5  External Backend Integration
P6  AI / ML Capability Factory
P7  Scheduler / Automation / Agent
P8  Product UI / Hi-fi / End-to-End Journeys
P9  Hardening / Security / DR / Performance
P10 Release Candidate / Production Gate
~~~

P0、P1、P2 可以部分并行。

P3 之后开始进入真正的工程实现。

---

# 3. 并行工作轨道

整个项目分为 7 条长期轨道。

## Track A — Architecture & Contract

负责：

- Domain Model；
- API；
- Event；
- State Machine；
- Registry；
- Capability Contract；
- Adapter Contract；
- Gate Contract；
- Versioning。

## Track B — Reuse & Integration

负责：

- CSGHub；
- MLflow；
- BentoML；
- ModelScope / ms-swift；
- SGLang / vLLM / llama.cpp；
- Gateway；
- Vector / Search；
- Workflow Backend；
- Virtualization Backend。

## Track C — UX / UI

负责：

- Roles；
- Golden Journeys；
- IA；
- Navigation；
- Low-fi；
- Design System；
- Hi-fi；
- Interactive Prototype；
- Usability；
- Frontend Implementation。

## Track D — Platform Core

负责：

- Go Control Hub；
- Registry；
- Policy；
- Gate；
- Scheduler；
- Resource Manager；
- Adapter Manager；
- Deployment Controller；
- Audit / Lineage。

## Track E — AI / ML Execution

负责：

- Python Workers；
- Model Intake；
- Training；
- Evaluation；
- Quantization；
- Data Factory；
- Research Reproduction；
- Specialized AI。

## Track F — Infrastructure / SRE

负责：

- VM；
- Container；
- PostgreSQL；
- S3；
- NATS；
- Edge；
- Secret；
- OCI Registry；
- IaC；
- CI/CD；
- Observability；
- Backup / DR。

## Track G — Verification / Release

负责：

- Contract Test；
- Integration Test；
- Security Test；
- Benchmark；
- E2E；
- Golden Journey；
- Release Gate；
- Recovery Test。

---

# 4. P0 — Reuse / Build Decision

目标：

> 明确第一版到底复用什么、二开什么、只做 Adapter 什么、自己构建什么。

## WP-P0-01 — Reuse / Build Matrix

### Scope

逐项判断：

~~~text
REUSE
EXTEND
ADAPTER
BUILD
REPLACE_LATER
RESTRICTED
REJECT
~~~

至少覆盖：

- CSGHub；
- MLflow；
- BentoML；
- ModelScope；
- ms-swift；
- SGLang；
- vLLM；
- llama.cpp；
- LiteLLM / alternative gateway；
- PostgreSQL；
- S3 / MinIO；
- NATS；
- OpenBao；
- Harbor；
- Caddy；
- libvirt；
- Vector DB；
- Search Engine；
- Workflow Engine。

### Output

docs/design/03-REUSE-BUILD-MATRIX.md

### Acceptance

每个候选必须回答：

1. 复用哪部分？
2. 不复用哪部分？
3. License 是否可接受？
4. 数据归谁？
5. Authority 是否会外泄？
6. Adapter 边界在哪里？
7. Exit Path 是什么？
8. 自主替代优先级如何？

## WP-P0-02 — Third-party Dependency Register

建立所有外部组件的：

- Exact Repo；
- Exact Revision；
- License；
- License Hash；
- Security Risk；
- Upstream Health；
- Internal Mirror；
- Replacement Candidate。

输出：

docs/design/04-DEPENDENCY-REGISTER.md

---

# 5. P1 — Domain Model & Contract

这是正式编码前最重要的一阶段。

## WP-P1-01 — Core Domain Model

冻结一级领域对象：

~~~text
Resource
Node
GPU
VM
Environment
Artifact
ModelAsset
DatasetAsset
Capability
Runtime
Deployment
Experiment
TrainingRun
EvaluationRun
Workflow
Agent
Tool
KnowledgeAsset
Index
Memory
Evidence
GateResult
Policy
Approval
Provider
Adapter
UpstreamDependency
~~~

输出：

~~~text
docs/design/10-DOMAIN-MODEL.md
contracts/schemas/
~~~

验收：

- 每个对象有稳定 ID；
- 有生命周期；
- 有 ownership；
- 有 lineage；
- 不引用第三方内部 DTO；
- 能覆盖 Frozen Functional Architecture。

## WP-P1-02 — Northbound API Contract

设计：

~~~text
/api/*
/v1/*
~~~

区分：

- AI Data Plane；
- Control Plane；
- Admin Plane。

输出：

~~~text
contracts/openapi/
docs/design/11-API-BOUNDARY.md
~~~

验收：

- OpenAPI 3.1；
- TypeScript / Go / Python Client 可生成；
- Third-party backend 替换不改变 Northbound Contract。

## WP-P1-03 — Event Contract

定义：

- Resource Event；
- Job Event；
- Deployment Event；
- Model Event；
- Dataset Event；
- Security Event；
- Approval Event；
- Audit Event。

必须包含：

- schema version；
- event id；
- producer；
- timestamp；
- correlation id；
- idempotency key；
- payload version。

## WP-P1-04 — State Machines

优先冻结：

- Model Lifecycle；
- Dataset Lifecycle；
- Deployment Lifecycle；
- Job Lifecycle；
- Experiment Lifecycle；
- Approval Lifecycle；
- VM Lifecycle；
- Dependency Risk Lifecycle。

## WP-P1-05 — Adapter Contract

第一批 Adapter（P1-D01 / P1-D02 裁决后）：

~~~text
AssetSourceAdapter
AssetHubAdapter
ExperimentAdapter
ServingAdapter
TrainingAdapter
ProviderAdapter
VectorAdapter
SearchAdapter
WorkflowAdapter
MessagingAdapter
VirtualizationAdapter
SecretAdapter
ObjectStorageAdapter
IdentityAdapter
OCIRegistryAdapter
~~~

规范输出：

~~~text
docs/design/15-ADAPTER-CONTRACT.md
contracts/adapters/
~~~

---

# 6. P2 — UX / UI Architecture

UI 设计从这一阶段正式开始。

P2 与 P0/P1 并行，但高保真视觉稿依赖 P1 的 Domain/API 基本稳定。

## WP-P2-01 — User Roles

第一批角色至少考虑：

- Platform Admin；
- AI Engineer；
- Data / Knowledge Engineer；
- Researcher；
- Application Developer；
- Operator / SRE；
- Security / Auditor；
- Approver；
- Viewer。

输出：

docs/ux/01-ROLES.md

## WP-P2-02 — Human-AI Responsibility Matrix

逐类动作明确：

~~~text
AI can execute
AI can propose only
Human approval required
Human only
~~~

重点：

- Production Promotion；
- Secret；
- Permission；
- Data Export；
- Model Publish；
- License Override；
- Security Exception；
- Destructive Delete。

## WP-P2-03 — Golden Journeys

第一批必须设计：

1. 接入一个外部模型并上线；
2. 导入 Dataset 并训练/微调；
3. 从论文/GitHub 项目复现实验；
4. 创建一个 Knowledge/RAG Capability；
5. GPU 高峰/低谷自动调度；
6. Candidate → Production；
7. 第三方 Backend 替换；
8. License 风险触发迁移；
9. Agent 自动执行任务、人工审批；
10. 故障后恢复到 LKG。

输出：

docs/ux/02-GOLDEN-JOURNEYS.md

## WP-P2-04 — Information Architecture

冻结一级导航候选：

~~~text
Home
AI Hub
Build
Run
Improve
Knowledge
Compute
Govern
~~~

全局入口：

~~~text
Needs Your Attention
Global Search
AI Operator
Notifications
Command Palette
~~~

输出：

docs/ux/03-INFORMATION-ARCHITECTURE.md

## WP-P2-05 — Low-fi Wireframes

第一轮只画核心页：

- Home；
- AI Hub；
- Model Detail；
- Dataset Detail；
- Training Run；
- Deployment；
- Compute / GPU；
- Experiment / Benchmark；
- Knowledge；
- Governance；
- Approval Inbox；
- AI Operator。

目标：

> 先确认任务路径，不追求视觉成品。

## WP-P2-06 — Design System Direction

> 状态：**Baseline Frozen v1.0**  
> 输出：docs/ux/06-DESIGN-SYSTEM.md + contracts/ui/design-tokens.v1.json

低保真稳定后再冻结：

- Color Tokens；
- Typography；
- Spacing；
- Density；
- Table；
- Form；
- Card；
- Status；
- Alert；
- Graph；
- Dark Mode；
- Accessibility。

## WP-P2-07 — Hi-fi Visual Prototype

> 状态：**Visual Baseline Complete v1.0**  
> 输出：`docs/ux/07-HI-FI-PROTOTYPE.md` + `docs/ux/prototype/`

依赖：

~~~text
P1 Domain/API Boundary
+
P2 Low-fi
+
Design System Direction
~~~

第一轮视觉成品稿已完成，覆盖 Home/Attention、AI Hub/Model Detail、Deployment Promotion/LKG、Experiment、Compute/GPU、Govern、Approval Inbox、AI Operator，并提供 Light/Dark 静态原型。

**P2 First-pass = COMPLETE。**

P3-01 Repository Skeleton 已满足启动条件；P3-05 Contract CI 作为 Foundation 首要保护线。

---

# 7. P3 — Foundation Skeleton

P3 是第一批真正平台代码。

## WP-P3-01 — Repository Skeleton

建立：

~~~text
apps/web
services/control-hub
services/gateway
workers/*
adapters/*
contracts/*
deploy/*
~~~

## WP-P3-02 — Go Control Hub Bootstrap

最小能力：

- health；
- version；
- config；
- structured logging；
- request id；
- OpenTelemetry；
- graceful shutdown；
- PostgreSQL connection；
- migration；
- NATS connection。

## WP-P3-03 — React App Bootstrap

包括：

- Router；
- Auth shell；
- Layout；
- Design Tokens；
- API Client generation；
- Query Client；
- Error Boundary；
- Loading / Empty / Error states。

## WP-P3-04 — Python Worker SDK

统一：

- Worker Manifest；
- Health；
- Capability Registration；
- Job Input / Output；
- Heartbeat；
- Evidence；
- Cancellation；
- Timeout。

## WP-P3-05 — Contract CI

CI 必须验证：

- OpenAPI；
- JSON Schema；
- generated clients；
- event compatibility；
- adapter contract；
- license/SBOM baseline。

---

# 8. P4 — Infrastructure & Runtime Foundation

- WP-P4-01 — PostgreSQL / Migration
- WP-P4-02 — S3 / Artifact Store
- WP-P4-03 — NATS / JetStream
- WP-P4-04 — Edge / TLS
- WP-P4-05 — Secret Broker
- WP-P4-06 — OCI Registry
- WP-P4-07 — VM / libvirt Adapter
- WP-P4-08 — Container / NVIDIA CDI
- WP-P4-09 — OpenTelemetry
- WP-P4-10 — IaC / Rebuild
- WP-P4-11 — Backup / Restore

P4 的验收不是“服务启动”，而是能够被 Control Hub 注册、探活、重建、备份和恢复。

---

# 9. P5 — External Backend Integration

第一批：

- WP-P5-01 — CSGHub Adapter
- WP-P5-02 — MLflow Adapter
- WP-P5-03 — BentoML Adapter
- WP-P5-04 — SGLang Adapter
- WP-P5-05 — vLLM Adapter
- WP-P5-06 — ModelScope Adapter
- WP-P5-07 — ms-swift Adapter
- WP-P5-08 — Gateway / Provider Adapter
- WP-P5-09 — Search / Vector Adapter
- WP-P5-10 — Workflow Backend Adapter

每一个必须通过统一 Contract Test。

---

# 10. P6 — AI / ML Capability Factory

- WP-P6-01 — Model Intake
- WP-P6-02 — Dataset Intake
- WP-P6-03 — Training Factory
- WP-P6-04 — Evaluation Factory
- WP-P6-05 — Quantization / Export
- WP-P6-06 — Generic AI Serving
- WP-P6-07 — Knowledge / Retrieval
- WP-P6-08 — Memory
- WP-P6-09 — Research Reproduction
- WP-P6-10 — Specialized / Industrial AI

---

# 11. P7 — Scheduler / Automation / Agent

- WP-P7-01 — Resource Inventory
- WP-P7-02 — GPU / VRAM Scheduler
- WP-P7-03 — Priority / Fair Share
- WP-P7-04 — Admission / Queue
- WP-P7-05 — Autoscaling / Load-Unload
- WP-P7-06 — Workflow Execution
- WP-P7-07 — Agent Control Plane
- WP-P7-08 — Human Approval
- WP-P7-09 — Recovery / Watchdog
- WP-P7-10 — Autonomous Replacement Candidate Flow

---

# 12. P8 — Product UI & End-to-End Journeys

P8 不再是“开始设计 UI”。

设计已在 P2 完成。

P8 是：

> 把已经验证的 Hi-fi / Design System 实现成真实产品。

- WP-P8-01 — App Shell
- WP-P8-02 — Home / Attention
- WP-P8-03 — AI Hub
- WP-P8-04 — Build Workspace
- WP-P8-05 — Run Workspace
- WP-P8-06 — Improve Workspace
- WP-P8-07 — Knowledge Workspace
- WP-P8-08 — Compute Workspace
- WP-P8-09 — Govern Workspace
- WP-P8-10 — AI Operator
- WP-P8-11 — Global Search / Command
- WP-P8-12 — Golden Journey E2E

---

# 13. P9 — Hardening

覆盖：

- Security；
- Prompt Injection；
- Supply Chain；
- License；
- SLO / Error Budget；
- Performance；
- HA；
- Backup / DR；
- Restore Drill；
- Chaos / Failure；
- Audit；
- Accessibility；
- Browser Compatibility；
- Upgrade / Migration；
- Backend Replacement Drill。

---

# 14. P10 — Release Candidate

最终 Gate：

~~~text
Architecture Contract
Technology Stack
Security
License
Data Portability
Backup / Restore
Performance
SLO
Golden Journeys
Human Approval
Backend Replacement
LKG Rollback
Documentation
~~~

全部通过后才进入 Production Baseline。

---

# 15. 第一批实际开工顺序

不是按 P0→P10 完全串行执行。

建议立即开始四条并行线：

~~~text
Lane 1
WP-P0-01 Reuse / Build Matrix

Lane 2
WP-P1-01 Core Domain Model

Lane 3
WP-P2-01 Roles
→ WP-P2-03 Golden Journeys
→ WP-P2-04 IA
→ WP-P2-05 Low-fi

Lane 4
只读盘点现有仓库资产
→ 为 P3 Foundation Skeleton 准备迁移/兼容计划
~~~

等 P0/P1 第一轮稳定后：

~~~text
P2 Hi-fi
+
P3 Coding
~~~

同时启动。

---

# 16. UI 设计时间点冻结

UI 不等后端完成。

时间关系正式冻结为：

~~~text
Functional Architecture Frozen
Technology Stack Frozen
        ↓
Roles / Journeys / IA
        ↓
Low-fi Wireframe
        ↓
Domain/API Boundary Stable
        ↓
Design System
        ↓
Hi-fi Visual Prototype
        ↓
Frontend Implementation
~~~

所以：

- **Low-fi：现在开始**
- **视觉成品稿：P1 Domain/API Boundary 基本稳定后立即开始**
- **Frontend Coding：Hi-fi 和 API Contract 第一版稳定后开始**

---

# 17. 本文之后的继续拆分规则

后续不再继续把本文件扩成几百页。

下一批文档按 Work Package 单独落盘：

~~~text
03-REUSE-BUILD-MATRIX.md
04-DEPENDENCY-REGISTER.md
10-DOMAIN-MODEL.md
11-API-BOUNDARY.md

docs/ux/
01-ROLES.md
02-GOLDEN-JOURNEYS.md
03-INFORMATION-ARCHITECTURE.md
04-HUMAN-AI-RESPONSIBILITY.md
05-LOW-FI-WIREFRAMES.md
06-DESIGN-SYSTEM.md
~~~

每完成一个设计包，再把它拆成执行 Task。

这保证“逐层收敛”，而不是一次性生成无法维护的大任务清单。

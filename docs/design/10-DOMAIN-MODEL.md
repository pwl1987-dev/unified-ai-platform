# Core Domain Model v0.1

> Work Package: **WP-P1-01 — Core Domain Model**  
> Status: **FIRST DOMAIN BASELINE — FROZEN FOR P1-02/P2 INPUT**  
> Date: **2026-09-25**  
> Authority: `docs/design/00-FUNCTIONAL-ARCHITECTURE.md`, `docs/design/01-TECHNOLOGY-STACK.md`, `docs/design/02-WORK-BREAKDOWN.md`  
> Dependency inputs: `docs/design/03-REUSE-BUILD-MATRIX.md`, `docs/design/04-DEPENDENCY-REGISTER.md`

---

# 1. 目的

本文件冻结平台第一层 Domain Model。

目标不是设计最终 PostgreSQL 表，而是先回答：

```text
平台长期稳定地认识什么对象？
谁拥有它？
它如何变化？
它从哪里来？
它产生了什么？
它当前是什么状态？
什么证据支持这个状态？
第三方 Backend 被替换后，这些对象是否仍然成立？
```

核心原则：

> **Domain belongs to the platform. Backend DTO belongs to the Adapter.**

因此：

- UI 只绑定本文 Domain Object / Read Model；
- Northbound API 只暴露我方 Contract；
- MLflow Run、Harbor Project、libvirt UUID、LiteLLM virtual key、SGLang endpoint 等都只是 external/backend reference；
- backend replacement 不得改变稳定 Domain ID；
- Evidence / Gate / Approval 不由第三方 backend 代替。

---

# 2. 本 WP 做什么 / 不做什么

## 2.1 本 WP 冻结

- 一级 Domain Object；
- stable ID 规则；
- common metadata；
- ownership；
- version semantics；
- status semantics；
- lineage；
- evidence relation；
- 第一轮 lifecycle；
- 核心对象关系；
- derived / authoritative 数据边界。

## 2.2 本 WP 不冻结

- 最终数据库表；
- SQL migration；
- REST URL；
- OpenAPI payload 全细节；
- Event Schema；
- 所有 State Machine transition guard；
- Adapter method signature；
- IAM/RBAC implementation；
- UI layout。

这些分别属于：

```text
P1-02 API
P1-03 Event
P1-04 State Machines
P1-05 Adapter Contract
P3/P4 implementation
P2 UX
```

---

# 3. Stable ID Contract

所有一级 Domain Object 必须由 **Control Hub** 生成稳定 ID。

## 3.1 规则

```text
<kind>_<uuidv7>
```

示例：

```text
model_0199...
dataset_0199...
deployment_0199...
evidence_0199...
approval_0199...
```

规范：

1. ID 创建后永不改变；
2. ID 永不复用；
3. ID 不从 display name 推导；
4. ID 不从第三方 backend ID 推导；
5. backend 被替换时 Domain ID 保持不变；
6. 删除对象后 ID 进入 tombstone/audit，不重新分配；
7. URL/path 可以变化，ID 不变化。

## 3.2 External Reference

第三方 ID 只能进入：

```text
ExternalRef {
  system
  kind
  value
  revision?
  url?
}
```

例如：

```text
system = "mlflow"
value  = "run-id-xxx"

system = "libvirt"
value  = "vm-uuid-xxx"

system = "harbor"
value  = "project/repo@sha256:..."
```

ExternalRef 永远不能替代 Domain ID。

---

# 4. Common Domain Envelope

所有一级对象共享最小 envelope：

```text
DomainObject
├── id
├── kind
├── schema_version
├── resource_version
├── name
├── description?
├── scope_ref?
├── owner_ref
├── created_at
├── updated_at
├── labels?
├── external_refs?
├── lineage?
├── evidence_refs?
├── policy_refs?
├── spec
└── status
```

## 4.1 字段语义

### id

稳定、不可变、平台生成。

### kind

一级对象类型；创建后不可改变。

### schema_version

表示 Contract Schema 版本。

它解决：

> 这个 payload 按哪一版 Domain Schema 解释？

### resource_version

单个对象的并发/变更版本。

- 每次 authoritative mutation 单调增加；
- 用于 optimistic concurrency；
- 不是业务版本；
- 不是 artifact version；
- backend observation 不得静默覆盖更高 resource_version。

### name

面向人的稳定名称，但允许修改；不可作为主键。

### scope_ref

对象所在作用域。

P1-D05 已在 WP-P1-02 收敛：Project 是平台内稳定的一等 Scope primitive；全局对象可以使用 system/global scope。Workspace 只属于 UX 组合层，Tenant 暂不进入 Stage-1 Domain，外部 Team 通过 IdentityAdapter/ExternalRef 映射。

### owner_ref

拥有该对象业务责任的 Principal reference；外部 Team 可以作为经过 IdentityAdapter 解析的 group reference 参与授权，但不能替代平台 Principal。

ServiceAccount 不再单独形成一级对象，而是 Principal.kind = SERVICE_ACCOUNT。

owner 不是“最后修改者”。

### lineage

描述对象从什么产生、由什么产生、替代什么。

### evidence_refs

支持当前状态/结论的 Evidence ID。

### policy_refs

直接约束该对象的 Policy snapshot/reference。

### spec

desired / declared / immutable design input。

### status

平台观察到的当前事实。

原则：

> **spec 表示意图；status 表示观察；Evidence 证明 status。**

---

# 5. Common Value Types

以下仍是跨对象 Value Type。P1-D05 已把 Project 与 Principal 提升为一等 Domain Object；OwnerRef / ScopeRef 继续作为跨对象引用形态。

## 5.1 OwnerRef

```text
OwnerRef {
  subject_type
  subject_id
  display_name?
}
```

subject 可以来自未来 IdentityAdapter，但平台必须保存稳定映射。

## 5.2 ScopeRef

```text
ScopeRef {
  scope_type
  scope_id
}
```

用于环境、项目、团队、租户等逻辑隔离。

## 5.3 Status

```text
Status {
  phase
  health?
  reason_code?
  message?
  observed_at
  observed_generation?
}
```

规则：

- `phase` 是机器可判定状态；
- `message` 不是 Authority；
- UI 不允许根据自由文本推导状态；
- backend raw status 必须由 Adapter 映射到平台 phase。

## 5.4 LineageEdge

```text
LineageEdge {
  relation
  object_id
  object_version?
  evidence_ref?
}
```

第一批 relation：

```text
DERIVED_FROM
PRODUCED_BY
CONSUMES
EVALUATES
TRAINS_FROM
DEPLOYS
INDEXES
GENERATED_FROM
SUPERSEDES
REPLACES
MIRRORS
VALIDATED_BY
```

## 5.5 EvidenceRef

只引用 `Evidence.id`。

任何关键 Gate 不接受无法定位 Evidence 的自由文本“已验证”。

---

# 6. Authority 分类

Domain 数据分三类。

## 6.1 Canonical

平台自身 Authority：

- stable ID；
- ownership；
- policy binding；
- lifecycle；
- approval；
- GateResult；
- canonical lineage；
- production promotion；
- capability mapping；
- dependency risk decision。

Canonical 默认存 PostgreSQL。

## 6.2 Immutable Artifact

内容事实：

- model weights；
- dataset shard；
- checkpoint；
- image/export；
- report；
- SBOM；
- raw benchmark result。

由 `Artifact` 通过 digest 管理，对象存储保存 payload。

## 6.3 Derived / Rebuildable

可从 Canonical + Artifact 重建：

- vector index；
- search index；
- cache；
- backend registry projection；
- read model；
- derived dashboard；
- external experiment projection。

Derived 丢失不得造成 canonical truth 丢失。

---

# 7. 一级 Domain Objects

第一批对象由 WBS 冻结的 27 个核心对象，加上 P1-D05 为 ownership / RBAC / Approval / Agent authority 收敛的两个基础对象组成：

```text
Project
Principal
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
```

不因当前 Qwen / SGLang / 4090 workload 改变对象集合。

## 7.1 Project

Project 是 Stage-1 的最小稳定 Scope Authority，用于 ownership、RBAC、Policy、Approval、quota 与 Agent execution scope。

- Stable ID：project_<uuidv7>
- Lifecycle：DRAFT → ACTIVE → SUSPENDED → ARCHIVED
- Project 不等于 UI Workspace；Workspace 可以组合多个视图但不能拥有 Authority。
- Stage-1 不引入 Tenant 对象；未来多租户需要独立 Architecture Change。

## 7.2 Principal

Principal 是平台稳定的 actor/identity primitive。

- Stable ID：principal_<uuidv7>
- kind：HUMAN | SERVICE_ACCOUNT
- Lifecycle：ACTIVE → SUSPENDED → REVOKED
- 外部 IdP/user/group ID 仅进入 external_refs。
- Team 保持 IdentityAdapter group reference，不新增 Team 一级对象。
- Agent 的真实副作用动作必须绑定 effective Principal；Agent 不能提升 Principal 权限。
- Secret value 不属于 Principal payload。

---

# 8. Compute / Environment Domain

## 8.1 Resource

### 定义

可被发现、计量、分配、调度或约束的资源抽象。

Resource 不是“所有东西的基类表”，而是 Scheduler 能理解的可分配资源语义。

### Stable ID

`resource_<uuidv7>`

### Ownership

平台/基础设施 owner。

### Lifecycle

```text
DISCOVERED
→ REGISTERED
→ READY
→ RESERVED / ALLOCATED
→ READY
→ DRAINING
→ MAINTENANCE
→ RETIRED
```

异常可进入：

```text
UNHEALTHY
UNKNOWN
```

### Version

资源描述变更增加 `resource_version`；实时 metrics 不增加 authoritative resource_version。

### Lineage

可关联物理来源、Node、VM、GPU、allocation。

### Evidence

inventory probe、health probe、topology probe。

---

## 8.2 Node

### 定义

可承载计算/存储/网络工作负载的机器实例，可以是物理机或平台认可的计算节点。

### Lifecycle

```text
DISCOVERED
→ REGISTERED
→ PROBING
→ READY
→ DRAINING
→ MAINTENANCE
→ RETIRED
```

旁路：

```text
UNHEALTHY
QUARANTINED
UNKNOWN
```

### Ownership

Infrastructure / Operator scope。

### Version

硬件/OS/driver profile 或管理属性改变时增加。

### Lineage

Node → GPUs / VMs / Environments / Evidence。

### Evidence

hardware inventory、driver probe、network probe、health、temperature/power observation。

---

## 8.3 GPU

### 定义

可独立盘点和调度的 Accelerator Resource。

不假定永远是 NVIDIA。

### Lifecycle

```text
DISCOVERED
→ READY
→ RESERVED
→ ALLOCATED
→ READY
→ DRAINING
→ MAINTENANCE
→ RETIRED
```

异常：

```text
DEGRADED
UNHEALTHY
QUARANTINED
```

### Ownership

所属 Node 的 infrastructure owner；allocation 期间记录 consumer reference。

### Version

静态能力/profile 变化时增加；实时利用率不作为对象新版本。

### Lineage

GPU → Node；allocation → Deployment/Run/Workflow。

### Evidence

VRAM、compute capability、health、ECC/Xid、功耗、温度、topology probes。

---

## 8.4 VM

### 定义

由 VirtualizationAdapter 管理的虚拟计算环境实例。

### Lifecycle

```text
PLANNED
→ PROVISIONING
→ STOPPED / RUNNING
→ DRAINING
→ STOPPED
→ DEPROVISIONING
→ RETIRED
```

异常：

```text
FAILED
UNKNOWN
```

### Ownership

Platform/Environment owner。

### Version

desired VM spec 变化增加；backend runtime observation 进入 status。

### Lineage

VM → source image Artifact / Node / Environment / workload。

### Evidence

provision receipt、backend observation、cloud-init evidence、health、destroy receipt。

### Invariant

libvirt UUID / VMware MoRef / Proxmox VMID 只存在 external_refs。

---

## 8.5 Environment

### 定义

可重现的执行环境声明。

可以描述：

- OS；
- driver；
- CUDA/ROCm；
- Python；
- packages；
- container image；
- runtime dependencies；
- environment variables 的非 secret 部分；
- compatible resource constraints。

### Lifecycle

```text
DRAFT
→ RESOLVING
→ READY
→ DEPRECATED
→ RETIRED
```

异常：

```text
FAILED
NON_REPRODUCIBLE
```

### Ownership

创建/维护环境的工程 owner。

### Version

Environment spec 变化产生新的 logical revision；已用于 Evidence 的 revision 不原地重写。

### Lineage

Environment → Artifact / UpstreamDependency / Runtime / Run / Deployment。

### Evidence

build receipt、dependency lock、SBOM、compatibility probe、rebuild proof。

---

# 9. Asset Domain

## 9.1 Artifact

### 定义

平台管理的一份不可变内容实体。

典型：

- model weights；
- dataset shard；
- checkpoint；
- OCI artifact；
- SBOM；
- benchmark raw result；
- report；
- export package。

### Stable ID

`artifact_<uuidv7>`

### Lifecycle

```text
DECLARED
→ INGESTING
→ AVAILABLE
→ ARCHIVED
→ RETIRED
```

异常：

```text
CORRUPT
MISSING
QUARANTINED
```

### Ownership

产生/导入它的 scope owner。

### Version

Artifact payload 本身不可变。

新内容 = 新 Artifact ID。

metadata correction 可以提升 resource_version，但不得改变 digest 对应内容。

### Lineage

source URI、producing Run、parent Artifact、mirror relation。

### Evidence

digest、size、media type、scan、signature/provenance、storage receipt。

### Invariant

```text
same Artifact.id => same content digest
```

---

## 9.2 ModelAsset

### 定义

模型作为可治理资产的逻辑实体，不等于某个 Runtime deployment。

### Lifecycle

```text
DISCOVERED
→ IMPORTING
→ CANDIDATE
→ VERIFIED
→ READY
→ DEPRECATED
→ RETIRED
```

限制/异常：

```text
RESTRICTED
QUARANTINED
FAILED
```

### Ownership

AI engineering / owning project。

### Version

模型 revision 必须显式；weights/config/tokenizer 变化形成新 revision 或新 ModelAsset lineage。

### Lineage

ModelAsset ← source/upstream；ModelAsset ← TrainingRun；ModelAsset → EvaluationRun / Deployment。

### Evidence

license、source digest、config snapshot、capability probe、evaluation、security scan。

### Invariant

ModelAsset 不包含 SGLang/vLLM 私有 deployment DTO。

---

## 9.3 DatasetAsset

### 定义

用于训练、评测、知识或研究的数据资产。

### Lifecycle

```text
DISCOVERED / DECLARED
→ INGESTING
→ CURATING
→ CANDIDATE
→ READY
→ DEPRECATED
→ RETIRED
```

限制：

```text
RESTRICTED
QUARANTINED
FAILED
```

### Ownership

Data / Knowledge owner。

### Version

数据内容、manifest、split、label policy 改变形成新 revision。

### Lineage

source → raw Artifact → transformation → Dataset revision → Run。

### Evidence

source/license、classification、dedupe、quality、PII/security、split manifest、digest。

### Invariant

Benchmark / Gold Set 不允许静默混入 Training split。

---

## 9.4 KnowledgeAsset

### 定义

可供检索、Agent、RAG 或知识工程使用的 canonical knowledge collection。

### Lifecycle

```text
DRAFT
→ INGESTING
→ CURATING
→ READY
→ UPDATING
→ READY
→ DEPRECATED
→ RETIRED
```

### Ownership

Data / Knowledge owner。

### Version

source set、ontology、chunk policy 的变化必须形成可追踪 revision。

### Lineage

KnowledgeAsset ← source Artifact/Dataset；KnowledgeAsset → Index / Capability。

### Evidence

source attribution、classification、quality、ingestion report、coverage。

### Invariant

Index 不是 KnowledgeAsset 本体。

---

## 9.5 Index

### 定义

从 canonical data/knowledge 构建出来的 **可重建派生物**。

类型可以是：

- vector；
- lexical/full-text；
- sparse；
- hybrid；
- graph projection；
- multimodal index。

### Lifecycle

```text
DECLARED
→ BUILDING
→ READY
→ STALE
→ REBUILDING
→ READY
→ DEPRECATED
→ RETIRED
```

异常：

```text
FAILED
CORRUPT
```

### Ownership

继承 source asset 的业务 owner；backend 运维由平台负责。

### Version

由以下组成的 build recipe 必须版本化：

- source revision；
- parser/chunker；
- embedding/model；
- backend adapter；
- backend version；
- index config。

### Lineage

Index → KnowledgeAsset/DatasetAsset/Artifact。

### Evidence

build manifest、document/chunk count、embedding digest、rebuild proof、quality benchmark。

### Invariant

> 删除 Index 后，必须能从 canonical source + recipe 重建。

---

# 10. Capability / Serving Domain

## 10.1 Capability

### 定义

平台向应用/Agent 暴露的稳定 AI 能力语义。

例如：

```text
coding
reasoning
vision
asr
embedding
meeting-assistant
auto
```

Capability 不等于模型名。

### Lifecycle

```text
DRAFT
→ CANDIDATE
→ AVAILABLE
→ DEPRECATED
→ RETIRED
```

### Ownership

Capability owner / service owner。

### Version

输入输出 contract、SLA class、semantic behavior 发生不兼容变化时产生 capability revision。

### Lineage

Capability → one/many Deployment；可依赖 ModelAsset/Tool/KnowledgeAsset/Provider。

### Evidence

contract tests、quality gate、latency/cost/reliability evidence。

### Invariant

调用方不需要知道实际 GPU、Runtime 或 Provider。

---

## 10.2 Runtime

### 定义

可执行 AI workload 的 runtime implementation/profile。

例如 SGLang、vLLM、llama.cpp 或其他 runtime。

### Lifecycle

```text
DISCOVERED
→ REGISTERED
→ PROBING
→ READY
→ DEPRECATED
→ RETIRED
```

异常：

```text
INCOMPATIBLE
UNHEALTHY
RESTRICTED
```

### Ownership

AI execution/platform owner。

### Version

runtime binary/image/config profile 必须精确版本化。

### Lineage

Runtime → UpstreamDependency / Environment / Adapter / Deployment。

### Evidence

capability probe、hardware compatibility、benchmark、SBOM、security scan。

### Invariant

Runtime 私有参数不能成为 Northbound API。

---

## 10.3 Deployment

### 定义

把一个 Capability implementation 放入某 Environment/Resource 并成为可路由实例的受控对象。

### Lifecycle

```text
DRAFT
→ CANDIDATE
→ PROVISIONING
→ STAGING
→ READY
→ PROMOTING
→ PRODUCTION
→ DRAINING
→ RETIRED
```

运行异常：

```text
DEGRADED
FAILED
ROLLING_BACK
```

LKG 在 P1-04 中收敛为 **经过验证的 Deployment revision designation**，不是与 PRODUCTION 互斥的 lifecycle phase。Production 可以同时指向一个 LKG revision；恢复完成后 phase 仍为 PRODUCTION，并记录 lkg_ref / recovered evidence。

### Ownership

service/capability owner；runtime operations 可委托 SRE。

### Version

Deployment spec 任何会影响运行行为的变化产生新 revision/generation。

### Lineage

Deployment → Capability / ModelAsset / Runtime / Environment / Provider / Artifact / Evidence。

### Evidence

build、probe、benchmark、GateResult、promotion receipt、health、rollback receipt。

### Invariant

```text
PRODUCTION requires successful GateResult + valid Approval when Policy requires
```

---

## 10.4 Provider

### 定义

一个可提供 AI/外部能力的逻辑 Provider endpoint/configuration。

Provider 可以是本地或外部，不等于具体供应商品牌。

### Lifecycle

```text
DECLARED
→ PROBING
→ AVAILABLE
→ DEGRADED
→ DISABLED
→ RETIRED
```

### Ownership

Platform Admin / service owner。

### Version

endpoint capability/policy/config 变化增加 resource_version；secret value 不进入 Provider object。

### Lineage

Provider → Adapter / Capability / UpstreamDependency / Evidence。

### Evidence

health probe、protocol conformance、usage/cost、privacy/security review。

### Invariant

Provider secret 只通过 Secret boundary 引用。

---

## 10.5 Adapter

### 定义

我方 Contract 与某 backend implementation 之间的可替换边界实现。

### Lifecycle

```text
DECLARED
→ IMPLEMENTED
→ PROBING
→ CONFORMANT
→ ACTIVE
→ DEPRECATED
→ RETIRED
```

异常：

```text
NON_CONFORMANT
RESTRICTED
FAILED
```

### Ownership

Platform Core / Integration owner。

### Version

Adapter package/image + contract version + backend compatibility range 必须固定。

### Lineage

Adapter → UpstreamDependency / Runtime / Provider / backend class。

### Evidence

contract test、compatibility matrix、replacement smoke、failure mapping test。

### Invariant

UI/API 不允许引用 Adapter 私有 DTO。

---

# 11. Experiment / Execution Domain

## 11.1 Experiment

### 定义

一个可重复、可比较的实验意图与 Contract。

### Lifecycle

```text
DRAFT
→ PLANNED
→ READY
→ RUNNING
→ COMPLETED
→ ARCHIVED
```

异常：

```text
BLOCKED
FAILED
CANCELED
```

### Ownership

Research / AI Engineering owner。

### Version

hypothesis、inputs、method、acceptance criteria 变化形成新 experiment revision。

### Lineage

Experiment → TrainingRun / EvaluationRun / Dataset / Model / Environment。

### Evidence

experiment contract、baseline、run evidence、analysis report。

---

## 11.2 TrainingRun

### 定义

一次具体训练/微调执行。

### Lifecycle

```text
QUEUED
→ ADMITTED
→ PREPARING
→ RUNNING
→ CHECKPOINTING
→ RUNNING
→ SUCCEEDED
```

旁路：

```text
PAUSED
PREEMPTED
FAILED
CANCELED
```

### Ownership

Experiment/AI Engineer。

### Version

Run 本身是执行实例，不“改写历史”。

retry/resume 必须记录 attempt / checkpoint lineage。

### Lineage

TrainingRun consumes Dataset/Model/Environment/Resource；produces Artifact/ModelAsset/Evidence。

### Evidence

resolved config、resource allocation、logs、metrics、checkpoint、output digest。

---

## 11.3 EvaluationRun

### 定义

一次对模型/Capability/Deployment 的评估执行。

### Lifecycle

```text
QUEUED
→ ADMITTED
→ PREPARING
→ RUNNING
→ SUCCEEDED
```

旁路：

```text
FAILED
CANCELED
INVALIDATED
```

### Ownership

AI Engineer / Research / Verification owner。

### Version

EvaluationRun 是不可重写历史；评测集或 rubric 变化必须产生新 run。

### Lineage

EvaluationRun evaluates ModelAsset/Deployment/Capability；consumes Dataset/Artifact；produces Evidence。

### Evidence

exact evaluator、dataset revision、environment、raw result、summary。

### Invariant

summary 不能替代 raw evidence。

---

## 11.4 Workflow

### 定义

由平台 Authority 管理的多步骤、可恢复、可审计执行计划。

### Lifecycle

```text
DRAFT
→ PLANNED
→ QUEUED
→ RUNNING
→ WAITING
→ RUNNING
→ SUCCEEDED
```

旁路：

```text
BLOCKED
PAUSED
FAILED
CANCELED
COMPENSATING
ROLLED_BACK
```

### Ownership

发起 scope owner + platform execution authority。

### Version

Workflow definition revision 与 Workflow execution instance 分离。

### Lineage

Workflow → Agent/Tool/Run/Approval/Gate/Evidence。

### Evidence

plan snapshot、step inputs/outputs、attempts、lease/fencing record、approval/gate results。

### Invariant

外部 Workflow Engine 只能执行，不拥有 Workflow semantic authority。

---

# 12. Agent / Tool Domain

## 12.1 Agent

### 定义

在受控权限下规划、调用 Tool、执行 Workflow 的自动化执行主体。

Agent 不是超级用户。

### Lifecycle

```text
REGISTERED
→ PROBING
→ AVAILABLE
→ BUSY
→ AVAILABLE
→ SUSPENDED
→ RETIRED
```

异常：

```text
UNHEALTHY
REVOKED
```

### Ownership

平台/团队 owner。

### Version

model/provider/tool policy/system instructions/capability manifest 的实质变化形成新 revision。

### Lineage

Agent → Provider/Capability/Tool/Workflow/Policy/Evidence。

### Evidence

capability probe、tool permission snapshot、execution trace、policy decision。

### Invariant

Agent 的 effective authority ≤ invoking principal + policy grant。

---

## 12.2 Tool

### 定义

Agent 或 Workflow 可以调用的受控动作 Contract。

例如：

- API；
- MCP；
- repository action；
- browser/computer action；
- data operation；
- infrastructure action。

### Lifecycle

```text
DECLARED
→ VERIFIED
→ AVAILABLE
→ RESTRICTED
→ DEPRECATED
→ RETIRED
```

### Ownership

Tool provider / platform integration owner。

### Version

input/output schema、副作用语义、权限需求变化必须产生新 version。

### Lineage

Tool → Adapter/Provider/UpstreamDependency/Policy。

### Evidence

contract test、permission test、side-effect classification、security review。

### Invariant

每个 Tool 必须声明 side-effect class。

---

# 13. Memory Domain

## 13.1 Memory

### 定义

可被 Agent/Workflow/Capability 长期使用的受控记忆集合。

它不是某个 vector database collection 的别名。

### Lifecycle

```text
ACTIVE
→ UPDATING
→ ACTIVE
→ ARCHIVED
→ RETIRED
```

限制：

```text
RESTRICTED
QUARANTINED
```

### Ownership

明确 scope/subject owner。

### Version

memory item changes必须有 revision/audit；冲突合并不能静默覆盖。

### Lineage

Memory ← source interaction/Evidence/KnowledgeAsset；Memory → Index/Agent context。

### Evidence

source reference、extraction method、confirmation/approval、revision history。

### Invariant

derived embedding/index 不等于 Memory canonical record。

---

# 14. Governance Domain

## 14.1 Evidence

### 定义

对某个事实、测试、执行、来源或观察的可验证记录。

Evidence 是整个平台 Promotion/Gate/Audit 的基础对象。

### Lifecycle

```text
CAPTURED
→ VALIDATED
→ ACTIVE
→ SUPERSEDED / ARCHIVED
```

异常：

```text
INVALID
REVOKED
```

### Ownership

产生 evidence 的系统/责任人；验证者单独记录。

### Version

Evidence payload 一旦用于 Gate 必须不可变。

修正 = 新 Evidence + supersedes relation。

### Lineage

Evidence → subject object + source Artifact + producer。

### Evidence

Evidence 自身通过 digest/signature/provenance 自证完整性。

### Invariant

失败 Evidence 不得删除以换取 PASS。

---

## 14.2 GateResult

### 定义

某个 Gate Contract 在某个时间点，对明确输入与 Evidence 集做出的机器可解释结果。

### Lifecycle

```text
EVALUATING
→ PASS / FAIL / BLOCKED
→ SUPERSEDED
```

### Ownership

Gate/Policy owner；结果产生者记录为 actor。

### Version

GateResult 不原地修改；重新评估生成新 GateResult。

### Lineage

GateResult → Policy/Gate version + Evidence set + subject revision。

### Evidence

输入 Evidence、本次 evaluator version、decision trace。

### Invariant

没有 Evidence 的 PASS 无效。

---

## 14.3 Policy

### 定义

约束平台行为、权限、预算、安全、数据、Promotion、自动化边界的版本化规则。

### Lifecycle

```text
DRAFT
→ REVIEW
→ ACTIVE
→ DEPRECATED
→ RETIRED
```

### Ownership

对应治理 authority。

### Version

Policy 修改必须形成 immutable revision；历史 GateResult 保留当时 policy snapshot reference。

### Lineage

Policy → subject scope / Approval / GateResult。

### Evidence

review/approval、change rationale、test evidence。

### Invariant

Agent 不得自行修改 Frozen/Active Policy 来让任务通过。

---

## 14.4 Approval

### 定义

需要人类承担责任的受控决策记录。

### Lifecycle

```text
REQUESTED
→ PENDING
→ APPROVED / REJECTED
```

其他：

```text
CHANGES_REQUESTED
CANCELED
EXPIRED
REVOKED
```

### Ownership

request owner + approver scope 分离记录。

### Version

Approval decision 不覆盖历史；re-request 建新 revision/record。

### Lineage

Approval → action/subject/Policy/GateResult/Evidence。

### Evidence

decision packet、approver、time、scope、reason、conditions。

### Invariant

AI/Agent final self-approval 永久禁止。Human requester 是否可以审批自己的低风险请求由 Separation-of-Duty Policy 决定；Production/Security/License/privileged action 默认要求独立 Human Approver。

---

# 15. Dependency Domain

## 15.1 UpstreamDependency

### 定义

任何会影响平台 build/runtime/data/license/security 的外部上游依赖记录。

### Lifecycle

```text
DISCOVERED
→ UNDER_REVIEW
→ ACCEPTED / RESTRICTED / REJECTED
→ ACTIVE
→ AT_RISK
→ MIGRATING
→ REPLACED
→ RETIRED
```

### Ownership

Integration / Security / owning workstream。

### Version

repo/release/license/security posture 变化生成新 revision/observation。

### Lineage

UpstreamDependency → Adapter / Runtime / Environment / Artifact。

### Evidence

exact repo/revision、license blob/hash、SBOM、advisory scan、mirror receipt、replacement evidence。

### Invariant

upstream name/tag 不足以成为 dependency evidence；必须可定位 exact revision/digest。

---

# 16. 对象验收矩阵

| Object | Stable ID | Ownership | Lifecycle | Version | Lineage | Evidence |
|---|---:|---:|---:|---:|---:|---:|
| Resource | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Node | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| GPU | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| VM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Environment | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Artifact | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ModelAsset | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| DatasetAsset | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Capability | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Runtime | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Deployment | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Experiment | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| TrainingRun | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| EvaluationRun | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Workflow | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Agent | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Tool | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| KnowledgeAsset | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Index | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Memory | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Evidence | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| GateResult | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Policy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Approval | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Provider | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Adapter | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| UpstreamDependency | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

# 17. 核心关系图

```text
UpstreamDependency
      │
      ├──────────────→ Adapter ──────────────→ Provider
      │                    │                     │
      │                    ├────→ Runtime        │
      │                    │        │            │
      ▼                    │        ▼            │
 Environment ← Artifact ←──┘    Deployment ←────┘
      ▲         ▲                   │
      │         │                   ▼
      │      ModelAsset ───────→ Capability
      │         ▲                   ▲
      │         │                   │
      │    TrainingRun         Tool / Agent
      │         ▲                   │
      │         │                   ▼
 DatasetAsset ──┴────→ Experiment → Workflow
      │                         │       │
      │                         ▼       ▼
      │                   EvaluationRun Approval
      │                         │       │
      ▼                         ▼       ▼
KnowledgeAsset ──→ Index ───→ Evidence → GateResult
      │
      ▼
    Memory
```

Compute side：

```text
Resource
  ├── Node
  │    ├── GPU
  │    └── VM
  │
  └── allocations consumed by
       Deployment / TrainingRun / EvaluationRun / Workflow
```

治理 side：

```text
Policy
  ├── constrains Domain Object
  ├── evaluates with Evidence
  ├── produces GateResult
  └── may require Approval
```

---

# 18. P1 裁决登记

P1 裁决的规范 Authority 已迁移到：

- docs/design/12-DECISION-REGISTER.md

本文件只保留结果摘要，避免裁决散落在 prose 中：

- P1-D01：RESOLVED — 使用 OCIRegistryAdapter；Harbor 只是可替换实现。
- P1-D02：RESOLVED — 拆分 AssetSourceAdapter 与 AssetHubAdapter。
- P1-D03：RESOLVED — Index 是可重建派生物，不是 Knowledge/Data Authority。
- P1-D04：RESOLVED — ProviderAdapter 与 ServingAdapter 分离，共享最小 capability conformance 语义。
- P1-D05：RESOLVED — Project、Principal 升格一等对象；ServiceAccount 是 Principal.kind；Team 外部映射；Workspace 非 Authority；Tenant 延后。
- P1-D06：RESOLVED — business revision 与 resource_version 永久分离。

任何后续修改以上裁决，必须更新 Decision Register，并满足其 Revisit Trigger。

---

# 19. UI / UX 输入

P2 现在可以稳定依赖以下概念：

## 19.1 UI 可直接展示

- Domain ID / name；
- lifecycle phase；
- owner；
- version/revision；
- health；
- lineage；
- Evidence；
- Gate；
- Approval；
- dependency risk。

## 19.2 UI 不直接展示为 Authority

- raw MLflow state；
- raw libvirt state；
- Harbor project state；
- LiteLLM team/key；
- SGLang/vLLM internal DTO；
- vector DB collection state。

这些只能作为：

```text
Backend Detail
Diagnostic Detail
External Reference
```

## 19.3 Detail Page 通用骨架

后续 Low-fi 的对象详情页至少应考虑：

```text
Header
  Name / Kind / Phase / Owner / Revision

Overview
  Desired Spec
  Current Status

Relationships
  Lineage / Depends On / Produced By

Evidence
  latest evidence + raw links

Governance
  Policy / Gate / Approval

Runtime / Backend
  Adapter / external refs

Audit
  changes / actor / timestamps
```

---

# 20. API 输入

WP-P1-02 应遵守：

1. Domain envelope 不暴露 backend DTO；
2. create/update 使用 stable Domain ID；
3. mutating request 支持 expected `resource_version`；
4. long-running mutation 返回 Workflow/Operation reference；
5. status 与 spec 分离；
6. Evidence/Gate/Approval 有独立资源；
7. external refs 只能出现在明确字段；
8. read model 可以组合，但 canonical mutation 必须回到一级对象 Contract。

---

# 21. Event 输入

WP-P1-03 应保证事件至少可表达：

```text
object_id
kind
resource_version
event_type
occurred_at
producer
correlation_id
causation_id
idempotency_key
schema_version
evidence_refs
```

事件不能只发 backend raw payload。

---

# 22. State Machine 输入

WP-P1-04 优先把本文 lifecycle 转为机器状态机：

- ModelAsset；
- DatasetAsset；
- Deployment；
- TrainingRun / EvaluationRun；
- Experiment；
- Approval；
- VM；
- UpstreamDependency；
- Workflow。

State Machine 必须再补：

- allowed transition；
- actor；
- guard；
- required evidence；
- required approval；
- timeout；
- retry；
- compensation/rollback。

---

# 23. Acceptance Criteria

WP-P1-01 完成条件：

- [x] 覆盖 WBS 冻结的 27 个核心 Domain Object，并按 P1-D05 增补 Project / Principal 两个基础对象；
- [x] 每个对象都有稳定 ID 规则；
- [x] 每个对象都有 ownership；
- [x] 每个对象都有 lifecycle；
- [x] 每个对象都有 version semantics；
- [x] 每个对象都有 lineage；
- [x] 每个对象都有 evidence relation；
- [x] spec / status 分离；
- [x] canonical / artifact / derived 三类事实分离；
- [x] Index 明确为可重建派生物；
- [x] Capability 与 Model/Runtime/Provider 解耦；
- [x] Deployment Promotion 依赖 Gate/Approval；
- [x] Agent Authority 不高于调用主体 + Policy；
- [x] 第三方 ID 只能作为 ExternalRef；
- [x] 没有引入第三方内部 DTO；
- [x] 新发现的 scope/identity 缺口已登记，不擅自改 Frozen Architecture。

---

# 24. Exit Condition

WP-P1-01 的 Exit Condition：

> P1-02 API、P1-03 Event、P1-04 State Machine、P1-05 Adapter，以及 P2 Golden Journey/IA/Low-fi，已经拥有同一套稳定的对象语言，不需要根据 CSGHub、MLflow、SGLang、vLLM、Harbor、libvirt 或其他单一第三方重新定义平台语义。

下一步不扩写本文件，而进入下一层 Contract。

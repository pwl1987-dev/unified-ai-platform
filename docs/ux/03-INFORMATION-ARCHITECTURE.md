# Information Architecture v1.0

> Work Package：**WP-P2-04 Information Architecture**
>
> 状态：**一级导航与全局入口 Frozen v1.0**
>
> 输入：User Roles + Golden Journeys + Domain Model + Human-AI Responsibility。
>
> 原则：导航按“用户要完成的任务”组织，不按数据库表、Backend 产品或技术组件组织。

# 1. IA 设计原则

## 1.1 一级导航冻结

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

这 8 个一级导航是任务域，不是权限域。Role 决定可见内容、默认落点和 mutation ability，但不复制第二套菜单。

## 1.2 不把第三方产品变成导航

禁止出现以下一级导航：

- MLflow
- CSGHub
- Harbor
- vLLM
- SGLang
- ModelScope
- libvirt
- LiteLLM

这些只作为 Adapter / Backend implementation detail 出现在对象详情或 diagnostics 中。

## 1.3 Domain Object ≠ Navigation Item

Domain Object 可以跨多个工作区出现。例如：

- Deployment 在 AI Hub 看“它提供什么能力”，在 Run 看“它现在如何运行”；
- ModelAsset 在 AI Hub 看资产详情，在 Improve 看实验和评测；
- GPU 在 Compute 是主体，在 Training Run 只是资源证据；
- Approval 在 Govern 管理，但也从任意 Attention item 进入。

导航表示工作意图，不表示对象唯一归属。

# 2. Global App Shell

全局 Shell 固定包含：

1. 当前 **Project Scope**；
2. 当前 **Environment**；
3. 当前 Principal / Acting as；
4. 一级导航；
5. Needs Your Attention；
6. Global Search；
7. AI Operator；
8. Notifications；
9. Command Palette。

Project/Environment 切换必须显式。任何有副作用操作在切换后都重新做 Policy / Responsibility Level 计算。

不允许：

- 在后台悄悄切 Project；
- 让 AI Operator 保留旧 Scope 执行新命令；
- 在 Production 与 Development 间只靠颜色区别。

# 3. Home

## 解决什么任务

回答：

> 今天平台是否健康？我现在最应该处理什么？最近发生了什么？

Home 是 task triage 与全局态势，不是把全部模块压缩成 dashboard。

## 高频 Role

- Platform Admin
- Operator / SRE
- Security / Auditor
- Approver
- AI Engineer
- Viewer

## Domain Objects

聚合 read model：

- Capability
- Deployment
- Workflow
- TrainingRun / EvaluationRun
- Resource / GPU
- Evidence / GateResult
- Approval
- UpstreamDependency

Home 不成为这些对象的 mutation Authority。

## Journey

- J05 GPU 调度
- J06 Candidate → Production
- J08 License Migration
- J10 Recover to LKG
- 其余 Journey 的 Attention 入口

## Home 必须有

- Needs Your Attention 摘要；
- Production health / degraded capabilities；
- active long-running Operations；
- GPU/compute pressure；
- pending Approvals；
- Gate blocked；
- dependency/license/security alerts；
- recent significant changes；
- LKG / rollback events。

## 不能放这里

- 大型资产目录；
- 完整实验编辑器；
- GPU 逐项调参；
- Policy 全量配置；
- 第三方 Backend admin console。

## Global interaction

Search 从 Home 可直达对象；Attention item 直接深链到动作上下文；AI Operator 可解释异常，但必须显示 Acting as/Scope/Environment。

---

# 4. AI Hub

## 解决什么任务

回答：

> 平台现在可以提供哪些 AI 能力？这些能力由哪些受控资产实现？

AI Hub 是 **Capability-first catalog + AI asset relationship**。

## 高频 Role

- AI Engineer
- Application Developer
- Data / Knowledge Engineer
- Researcher
- Platform Admin
- Viewer

## Domain Objects

- Capability
- ModelAsset
- Provider
- Deployment（能力视角）
- Artifact
- Adapter / ExternalRef（detail only）
- Evidence / GateResult

## Journey

- J01 外部模型上线
- J04 Knowledge/RAG
- J07 Backend Replacement

## 核心信息架构

~~~text
AI Hub
├── Capabilities
├── Models
├── Providers
└── Assets / implementations
~~~

默认首页先展示 Capability，不先展示模型列表。

## 不能放这里

- GPU placement；
- Training queue；
- Governance exception；
- backend-specific runtime flags 作为一级字段；
- secret plaintext。

## Global interaction

Search 支持 capability alias / stable ID；AI Operator 可以“比较这两个 implementation”，但不能直接 bypass Promotion。

---

# 5. Build

## 解决什么任务

回答：

> 如何把数据、模型、环境和方法组织成一个可执行构建/训练输入？

Build 是资产准备和工程创建区。

## 高频 Role

- AI Engineer
- Data / Knowledge Engineer
- Researcher

## Domain Objects

- DatasetAsset
- ModelAsset（input/candidate）
- Environment
- Artifact
- TrainingRun（create context）
- Experiment（create context）
- Workflow

## Journey

- J02 Dataset → Training
- J03 Research Reproduction
- J04 Knowledge/RAG（source preparation）

## 核心分区

~~~text
Build
├── Datasets
├── Training setups
├── Environments
├── Reproduction inputs
└── Build artifacts
~~~

## 不能放这里

- Production Promotion；
- live production health；
- global Policy override；
- third-party CI/CD console。

## Global interaction

Needs Your Attention 显示 dataset classification、build failure、missing provenance；AI Operator 可生成 training/reproduction plan，实际创建 Run 仍走 northbound contract。

---

# 6. Run

## 解决什么任务

回答：

> 哪些 AI workload 正在运行？服务是否健康？部署如何晋级、回滚和恢复？

Run 是 Deployment / live workload / Operation 的运行态工作区。

## 高频 Role

- Operator / SRE
- AI Engineer
- Platform Admin

## Domain Objects

- Deployment
- Capability（runtime association）
- Workflow / Operation
- TrainingRun / EvaluationRun（running view）
- Environment
- Evidence
- GateResult

## Journey

- J01 外部模型上线
- J05 GPU 调度
- J06 Candidate → Production
- J07 Backend Replacement
- J10 Recover to LKG

## 核心分区

~~~text
Run
├── Deployments
├── Live workloads
├── Operations
├── Rollouts
└── Recovery / LKG
~~~

## 不能放这里

- 模型源发现；
- Dataset canonical editing；
- License override final decision；
- GPU inventory master view。

## Global interaction

Attention 对 rollout regression / failed operation / recovery failure 强提醒。AI Operator 可执行已授权恢复，但显示 LKG、Gate、Approval。

---

# 7. Improve

## 解决什么任务

回答：

> 当前能力能否更好？哪个 candidate 值得继续？实验结论是否真实？

Improve 是 experiment / evaluation / benchmark / optimization 工作区。

## 高频 Role

- Researcher
- AI Engineer
- Data / Knowledge Engineer
- Operator / SRE（性能问题时）

## Domain Objects

- Experiment
- EvaluationRun
- TrainingRun（comparison）
- Evidence
- GateResult
- ModelAsset revision
- Capability candidate
- UpstreamDependency（research context）

## Journey

- J01 model evaluation
- J03 Research Reproduction
- J04 RAG evaluation
- J06 Promotion evidence
- J07 Backend A/B

## 核心分区

~~~text
Improve
├── Experiments
├── Evaluations
├── Benchmarks
├── Comparisons
└── Evidence / Pareto
~~~

## 不能放这里

- 通过改 threshold 直接 Promotion；
- 删除失败实验；
- Production traffic control；
- hidden benchmark filter。

## Global interaction

Search 可从 Model/Capability 进入相关 Experiment；AI Operator 可解释 Evidence、提出下一轮 experiment，不可为获得 PASS 降 Gate。

---

# 8. Knowledge

## 解决什么任务

回答：

> 平台依据哪些知识回答？来源、索引、质量和更新状态是什么？

## 高频 Role

- Data / Knowledge Engineer
- AI Engineer
- Application Developer
- Security / Auditor（敏感源）

## Domain Objects

- KnowledgeAsset
- Index
- DatasetAsset
- Capability
- Evidence
- Policy

## Journey

- J04 Knowledge/RAG

## 核心分区

~~~text
Knowledge
├── Knowledge Assets
├── Sources
├── Indexes
├── Retrieval evaluation
└── RAG capabilities
~~~

## 不能放这里

- 把 Vector DB collection 当 Knowledge authority；
- secret；
- Production approval；
- arbitrary provider configuration。

## Global interaction

Attention 处理 stale source、index rebuild failure、classification issue；AI Operator 可解释 source lineage 和发起 rebuild。

---

# 9. Compute

## 解决什么任务

回答：

> 算力在哪里、是否健康、被谁占用、下一步如何调度？

## 高频 Role

- Operator / SRE
- Platform Admin
- AI Engineer
- Researcher（read-heavy）

## Domain Objects

- Resource
- Node
- GPU
- VM
- Environment
- Deployment / Run refs
- Policy（scheduler view）
- Evidence

## Journey

- J02 Training
- J03 Reproduction
- J05 GPU Scheduling
- J10 Recovery

## 核心分区

~~~text
Compute
├── Overview
├── Nodes
├── GPUs
├── VMs / Environments
├── Allocations
└── Capacity / scheduling
~~~

## 不能放这里

- vendor GPU telemetry 直接变成 Domain schema；
- model quality Gate；
- capability catalog；
- privileged hypervisor side channel。

## Global interaction

Search 可用 node/gpu ID；Attention 处理 unhealthy、thermal/power、starvation；AI Operator 的 drain/reboot 等动作必须按责任等级。

---

# 10. Govern

## 解决什么任务

回答：

> 谁能做什么？为什么允许或阻止？哪些风险和批准正在等待？

## 高频 Role

- Platform Admin
- Security / Auditor
- Approver
- Operator / SRE

## Domain Objects

- Policy
- Approval
- GateResult
- Evidence
- Adapter
- Provider
- UpstreamDependency
- Principal / Project
- Audit read model

## Journey

- J01 Production approval
- J06 Candidate → Production
- J07 Backend Replacement
- J08 License Migration
- J09 Agent + Human Approval

## 核心分区

~~~text
Govern
├── Approval Inbox
├── Policies
├── Gates
├── Dependencies / License
├── Adapters / Providers
├── Access / Principals
└── Audit / Evidence
~~~

## 不能放这里

- 直接编辑 backend DB；
- secret plaintext；
- “force pass”；
- AI self-approval；
- arbitrary admin command console。

## Global interaction

Needs Your Attention 与 Approval Inbox 双向同步，但 Attention 是聚合入口，Approval Inbox 才是正式人类决策表面。

---

# 11. Needs Your Attention

这是全局最重要的行动聚合入口，但不是 Notification feed。

一个 item 必须满足至少一个：

- Human decision required；
- Gate blocked；
- production health risk；
- irreversible deadline；
- retry/budget exhausted；
- dependency/license/security risk；
- LKG/rollback issue；
- data classification ambiguity；
- long-running workflow requires intervention。

每个 item 必须显示：

- What happened
- Why it matters
- Affected Project/Environment
- Domain Object
- Responsibility Level
- Evidence
- Required human role
- Deadline/expiry（如有）
- Safe primary action
- Dismiss/snooze 规则

禁止把普通“任务完成”塞进 Attention。

# 12. Global Search

Search 是跨域 read surface。

第一批 result type：

- Capability
- ModelAsset
- DatasetAsset
- Deployment
- Experiment
- TrainingRun / EvaluationRun
- KnowledgeAsset
- Resource / Node / GPU
- Evidence / GateResult
- Approval
- Provider / Adapter / Dependency
- Project / Principal

结果显示 stable Domain ID；ExternalRef 只作为 secondary metadata。

Search 不提供隐式 mutation。

# 13. AI Operator

AI Operator 是全局任务协作面，不属于某个一级导航，也不是超级管理员。

固定头部必须显示：

~~~text
Acting as
Project Scope
Environment
Responsibility Level
Policy context
~~~

所有 proposed mutation 必须显示：

- proposed action；
- affected objects；
- side effects；
- Evidence destination；
- Gate；
- Approval；
- rollback/LKG；
- estimated resource/budget impact。

AI Operator 可以跨导航理解上下文，但执行仍调用同一 Northbound API。

# 14. Notifications

Notifications 是“发生了什么”的信息流，包含：

- operation completed；
- run finished；
- comment/mention；
- scheduled report；
- low-risk status change。

如果事件需要人做决定，必须同时或直接进入 Needs Your Attention，而不能只发 Notification。

# 15. Command Palette

Command Palette 是快捷导航/动作入口，不是 admin shell。

允许：

- 跳转对象；
- 创建常规资源；
- 触发当前 Principal 本来就能执行的 R0 action；
- 打开 AI Operator；
- 打开 Approval/Attention context。

禁止：

- bypass Approval；
- bypass Gate；
- raw backend command；
- secret reveal；
- hidden destructive mutation。

# 16. Role → Default Landing

| Role | Default landing | Secondary |
|---|---|---|
| Platform Admin | Home | Govern / Compute / Run |
| AI Engineer | AI Hub | Build / Improve / Run |
| Data / Knowledge Engineer | Knowledge | Build / AI Hub |
| Researcher | Improve | Build / AI Hub |
| Application Developer | AI Hub | Home |
| Operator / SRE | Home | Run / Compute |
| Security / Auditor | Govern | Home |
| Approver | Home / Approval Inbox | Govern |
| Viewer | Home | AI Hub |

Landing 是默认路径，不是访问边界。

# 17. Object → Primary Work Surface

| Object | Primary | Secondary |
|---|---|---|
| Project / Principal | Govern | Global context |
| Capability | AI Hub | Run / Improve |
| ModelAsset | AI Hub | Build / Improve |
| DatasetAsset | Build | Knowledge / Improve |
| Deployment | Run | AI Hub / Compute |
| Experiment / EvaluationRun | Improve | Build |
| TrainingRun | Build / Improve | Run / Compute |
| KnowledgeAsset / Index | Knowledge | Build / Improve |
| Resource / Node / GPU / VM | Compute | Run |
| Approval / Policy / Dependency | Govern | Home/Attention |
| Evidence / GateResult | contextual | Govern / Improve |
| Workflow / Operation | Run/contextual | Home |

Evidence 没有单独一级导航，因为它必须嵌入决策上下文；Govern/Improve 提供聚合查询。

# 18. URL / Routing Baseline

路由表达平台对象，不表达 backend 产品。

推荐：

~~~text
/home
/ai-hub/capabilities
/ai-hub/models
/build/datasets
/build/training
/run/deployments
/run/operations
/improve/experiments
/improve/evaluations
/knowledge/assets
/knowledge/indexes
/compute/gpus
/compute/nodes
/govern/approvals
/govern/policies
/govern/dependencies
/govern/access
~~~

详情使用 stable Domain ID：

~~~text
/run/deployments/{deployment_id}
~~~

禁止：

~~~text
/vllm/...
/mlflow/...
/harbor/...
/gpu/0-as-canonical-id
~~~

# 19. Breadcrumb / Cross-domain Rule

跨域对象不复制详情页。

例如：

~~~text
Capability Detail
→ implementation Deployment link
→ Run / Deployment Detail
→ evidence link
→ contextual Evidence drawer/detail
~~~

返回路径保留来源 context，但 canonical object URL 唯一。

# 20. Permission / Empty-state Rule

导航可见 ≠ 有 mutation 权限。

用户可看到某工作区但无权限时：

- read view 正常展示；
- mutation control disabled/hidden according to security policy；
- 必须说明“需要什么 Role / Approval”，而不是伪装成 backend error。

真正无对象时使用 Empty State；权限不足不使用 Empty State。

# 21. IA 对 Contract Gap 的处理

P2-03 的 15 个 Contract Gap 不改变一级导航。

它们会影响：

- action 是否可真正执行；
- detail page 是否有完整 read model；
- P3 coding readiness。

P2-05 Low-fi 必须把尚未冻结的 action 标为 Contract Pending，而不能画成“已可执行”的假按钮。

# 22. Acceptance Criteria

- [x] 八个一级导航全部由 Role + Journey 推导。
- [x] 每个导航说明 task / Role / Domain / Journey / forbidden content。
- [x] 全局 Search / Attention / AI Operator / Notification / Command Palette 边界明确。
- [x] 第三方 Backend 没有成为一级导航或 Authority。
- [x] Project/Environment/Acting as 成为全局 context。
- [x] Approval Inbox 与 Needs Your Attention 职责分离。
- [x] Evidence 作为 contextual object，不制造孤立 Evidence 产品。
- [x] Command Palette 不形成权限旁路。
- [x] 路由使用 stable Domain ID，不使用 ExternalRef。
- [x] 已给 P2-05 Low-fi 明确页面与全局 Shell 输入。

# 23. Exit Condition

WP-P2-04 完成。一级导航与全局入口冻结；下一步直接进入 WP-P2-05 Low-fi Wireframes。

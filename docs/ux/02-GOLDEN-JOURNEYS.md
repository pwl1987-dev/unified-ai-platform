# Golden Journeys v1.0

> Work Package：**WP-P2-03 Golden Journeys**
>
> 状态：**Baseline Frozen for IA / Low-fi**
>
> 上位 Authority：
> - docs/design/00-FUNCTIONAL-ARCHITECTURE.md
> - docs/design/10-DOMAIN-MODEL.md
> - docs/design/11-API-BOUNDARY.md
> - docs/design/12-DECISION-REGISTER.md
> - docs/ux/01-ROLES.md
> - docs/ux/04-HUMAN-AI-RESPONSIBILITY.md
>
> 目标：用真实任务流验证 Domain / API / Human-AI responsibility 是否能覆盖平台第一阶段产品，而不是围绕菜单或数据库表设计 UI。

## 0. 统一旅程规则

所有 Journey 都遵守：

~~~text
Goal
→ Plan / Proposal
→ Domain mutation or Operation
→ Evidence
→ Gate
→ Approval where required
→ Execute
→ Verify
→ Promote / Complete
→ Rollback or LKG when necessary
~~~

共同不变量：

1. AI Operator 继承 Current User + Role + Project Scope + Environment + Policy。
2. AI suggestion 与 executed action 必须在 UI 和 Evidence 中区分。
3. R0/R1/R2/R3 是动作级责任，不是某个角色永久等级。
4. 第三方 Backend 只提供 implementation observation，不拥有 Domain Authority。
5. Production Promotion、backend cutover、敏感导出、权限提升等不得 self-approve。
6. 任何 long-running action 使用 Operation / Workflow reference。
7. failed Evidence 不删除，只能 supersede / invalidate with reason。
8. LKG 必须是已通过 Gate、可定位 Evidence、可恢复的 Last Known Good，而不是“最近一次看起来正常”。

---

# Journey 01 — 接入外部模型并上线

| Field | Definition |
|---|---|
| Primary Actor | AI Engineer |
| Supporting Roles | Platform Admin、Operator/SRE、Security/Auditor、Approver、Application Developer |
| User Goal | 把一个外部模型来源接入平台，完成验证并以 Capability 形式对业务提供稳定服务 |
| Entry Condition | Project 已存在；操作者有模型接入权限；AssetSource/Provider/Serving Adapter 至少一个候选可用 |
| Domain Objects | Project、Principal、ModelAsset、Artifact、Capability、Provider、Adapter、Deployment、EvaluationRun、Evidence、GateResult、Approval、Workflow |
| Exit Condition | Production Capability 可从 /v1 调用，Deployment 状态与 Gate/Approval/Evidence 可追溯，Backend 可替换 |

## Main Flow

1. AI Engineer 在 AI Hub 选择“接入模型”，提供 source URI / provider candidate / license context。
2. AI Operator 以当前 Principal + Project Scope 生成 intake plan，先做只读 source/license/provenance probe。
3. 平台通过 AssetSourceAdapter 拉取 metadata；如为远程 API，则通过 ProviderAdapter candidate onboarding。
4. Control Hub 创建 ModelAsset stable ID，保存 ExternalRef，但不沿用 source model ID 作为主键。
5. 系统执行 capability probe、兼容性、license、安全、最小质量与成本评测，形成 EvaluationRun + Evidence。
6. 通过初始 Gate 后创建 Candidate Deployment；Serving/Provider Backend 只返回 observation 与 runtime evidence。
7. Capability 绑定 candidate implementation，Application Developer 可在非生产环境使用 /v1/responses 或 /v1/chat/completions 做 smoke。
8. 申请 Candidate → Production；系统检查 GateResult、LKG、rollout plan 与 Approval。
9. Approver 做 R3 最终 Approval decision；批准后系统执行 R2 已批准 rollout。
10. SRE 观察 canary/progressive rollout，验证 SLA 与 error budget；成功后 Production Capability 生效。

## AI actions

- R0：source discovery、metadata normalization、capability probe、benchmark、Evidence 汇总。
- R1：推荐运行方式、成本/质量 trade-off、promotion proposal。
- R2 执行阶段：在 Human Approval 后执行 rollout。
- AI 不得决定最终 Approval，不得把 backend model 名称固化为 Capability contract。

## Human actions

- AI Engineer 定义业务目标/质量需求并确认 candidate。
- Security/Auditor 处理高风险 license/security 问题。
- Approver 做最终 Production Promotion decision。
- SRE 在 rollout 异常时决定是否继续或进入 LKG policy。

## R0/R1/R2/R3 transition

~~~text
Discover/Probe R0
→ Production proposal R1
→ Approval decision R3
→ Approved rollout execution R2
→ bounded observation/recovery R0
~~~

## Evidence produced

- source/provenance/license Evidence；
- capability probe；
- EvaluationRun metrics；
- runtime/deployment readiness；
- GateResult；
- Approval decision；
- rollout/canary Evidence；
- production verification。

## Gate / Approval

Gate 至少覆盖 quality、security、license、runtime readiness、rollback/LKG。Production 必须 R2 + Human R3 decision。

## Failure path / Retry / Rollback

- source fetch 失败：按 Adapter retry policy 重试，不创建伪 ModelAsset success。
- capability probe 失败：candidate 保持 FAILED/BLOCKED，可修 spec 后重跑。
- canary 失败：停止晋级，回滚 LKG；失败 Evidence 保留。
- provider outage：若 Policy 允许，可切备用 implementation；否则 Capability 标记 degraded/unavailable。

## UI screens touched

Home → AI Hub → Model Detail → Experiment/Benchmark → Deployment → Governance/Approval Inbox → Home/Attention。

## API capability required

已覆盖：
- POST /api/v1/providers
- POST /api/v1/runs
- GET /api/v1/runs/{run_id}
- POST /api/v1/deployments/{deployment_id}:promote
- GET /api/v1/operations/{operation_id}
- GET /api/v1/evidence/{evidence_id}
- POST /api/v1/approvals/{approval_id}:decide
- POST /v1/responses、/v1/chat/completions

Contract Gap：
- **CG-01 ModelAsset intake action family**：需要统一 asset intake/action contract，但不要求现在展开全部 CRUD。

## Third-party boundary

ModelScope/HF/CSGHub/Provider/SGLang/vLLM/BentoML 等都只经 Adapter；任何 external ID、endpoint、job ID 都不得成为 ModelAsset/Deployment/Capability Authority。

## Needs Your Attention trigger

- license/security risk；
- Gate BLOCKED；
- Approval pending；
- rollout regression；
- provider/backend unavailable；
- Capability 无健康 production implementation。

---

# Journey 02 — 导入 Dataset 并训练/微调

| Field | Definition |
|---|---|
| Primary Actor | Data / Knowledge Engineer |
| Supporting Roles | AI Engineer、Security/Auditor、Approver、Operator/SRE |
| User Goal | 导入可追溯 Dataset，完成治理并启动可恢复训练/微调，产出可评估 ModelAsset revision |
| Entry Condition | Project 可用；数据来源允许导入；训练环境与资源 Policy 可用 |
| Domain Objects | DatasetAsset、Artifact、Environment、TrainingRun、Workflow、ModelAsset、Evidence、GateResult、Approval、Resource/GPU |
| Exit Condition | 新 ModelAsset business revision 与训练 lineage/Evidence 完整，可进入 Evaluation/Promotion |

## Main Flow

1. Data Engineer 从 Build/Dataset 发起导入，声明 source、用途、分类、license/consent。
2. AI 自动做 schema/profile/dedupe/PII/license checks，先进入 quarantine。
3. 人确认数据 classification 与不确定项；高风险变更进入 R2。
4. Control Hub 固化 DatasetAsset business revision 与 content hash，不把 object-store path 当 revision。
5. AI Engineer 创建 TrainingRun spec：dataset revision、base model revision、environment、method、budget、checkpoint policy。
6. Scheduler 在 Policy 下分配 GPU；长任务返回 Operation/Workflow。
7. 训练过程持续记录 checkpoint、metrics、resource usage、失败原因和 Evidence。
8. 中断时从受验证 checkpoint resume；成功产出 Artifact + 新 ModelAsset revision。
9. 自动启动 EvaluationRun；若 quality/data/license Gate 失败则不能 Promotion。
10. 训练产物进入 Candidate，后续复用 Journey 06。

## AI actions

R0：profiling、dedupe、数据质量建议、训练计划候选、checkpoint/resume、metric collection。
R1：建议超预算扩容、classification 降级、训练 recipe 重大变更。
R2：敏感数据用途变更、外发、生产预算突破需要批准。
R3：涉及最终 policy/license exception 的决定由人完成。

## Human actions

Data owner 确认 data intent/classification；AI Engineer 确认训练目标；Approver 处理高风险预算/外发/exception。

## R0/R1/R2/R3 transition

~~~text
Import quarantine R0
→ classification exception proposal R1
→ sensitive approval R2/R3 where applicable
→ training execution R0 within budget
→ candidate result
~~~

## Evidence produced

source/license、classification、quality profile、dedupe report、Dataset revision hash、TrainingRun config、checkpoint lineage、GPU usage、training metrics、output artifact hash、EvaluationRun。

## Gate / Approval

Data Gate、Budget Gate、Training completion Gate、post-training Evaluation Gate。普通内网训练可 R0；敏感数据外部传输必须 R2。

## Failure path / Retry / Rollback

- import/parser 失败：保留 quarantine Evidence，修 Adapter 后重试。
- OOM/worker crash：bounded retry，必要时 checkpoint resume。
- 数据污染：标记 revision INVALID/SUPERSEDED，不能删除旧 Evidence。
- 新模型质量回退：不替换 LKG。

## UI screens touched

Build → Dataset Detail → Training Run → Compute/GPU → Experiment/Benchmark → Model Detail → Needs Your Attention。

## API capability required

已覆盖：
- POST /api/v1/runs
- GET /api/v1/runs/{run_id}
- GET /api/v1/resources/gpus
- GET /api/v1/operations/{operation_id}
- GET /api/v1/evidence/{evidence_id}

Contract Gap：
- **CG-02 DatasetAsset intake/revision contract**
- **CG-03 Training checkpoint/resume action semantics**，最终应由 P1-04 State Machine + P1-05 TrainingAdapter 收敛。

## Third-party boundary

Object Storage、ms-swift/Trainer、MLflow 等不能定义 Dataset revision、TrainingRun identity 或 Gate。

## Needs Your Attention trigger

敏感数据不确定、训练反复失败、预算越界、checkpoint 无法恢复、quality regression、数据 license 改变。

---

# Journey 03 — 从论文/GitHub 项目复现实验

| Field | Definition |
|---|---|
| Primary Actor | Researcher |
| Supporting Roles | AI Engineer、Security/Auditor、Operator/SRE |
| User Goal | 在隔离、可复现环境中验证论文/项目结论并与内部 baseline 比较 |
| Entry Condition | source revision 可定位；依赖与 license 可审计；Sandbox/Development 资源可用 |
| Domain Objects | Experiment、Environment、Artifact、EvaluationRun、Workflow、UpstreamDependency、Evidence、GateResult、Resource |
| Exit Condition | Reproduction result 可复现，有 baseline 对比和 adoption/reject 结论，不污染 Production |

## Main Flow

1. Researcher 提交 paper/repo/revision 与要验证的 claim。
2. AI Operator 生成 reproduction contract：source pin、environment、dataset、metric、acceptance threshold、budget。
3. Security scan dependency/license/supply-chain，未知二进制进入隔离。
4. Control Hub 创建 Experiment stable ID 和 Environment spec。
5. Workflow 在隔离环境执行 build/run/evaluation。
6. EvaluationRun 与当前 baseline 使用同一 metric contract，避免“换指标获胜”。
7. AI 形成差异分析、ablation 候选、风险与 adoption recommendation。
8. Researcher 审阅结论；若要引入生产链，则进入 Adapter/Dependency onboarding 与后续 Gate。

## AI actions

R0：paper/repo parsing、plan、environment manifest、benchmark、evidence extraction。
R1：adoption recommendation、architecture change proposal。
不得直接把实验依赖加入 Production critical path。

## Human actions

Researcher 确认 claim/acceptance；Security 处理高风险 dependency；Architecture/Approver 对生产引入单独裁决。

## R0/R1/R2/R3 transition

Sandbox reproduction 多数 R0；引入生产依赖从 R1 升级到 R2/R3，取决于 license/security/closed-source 风险。

## Evidence produced

source revision、dependency snapshot、SBOM/license、environment manifest、run logs、metrics、ablation、baseline comparison、final reproduction verdict。

## Gate / Approval

Reproducibility Gate、Supply-chain Gate、License Gate。实验成功不等于生产批准。

## Failure path / Retry / Rollback

不可复现时保留 NOT_REPRODUCED Evidence；允许修 environment 后新 iteration；不得改 acceptance threshold 掩盖失败。

## UI screens touched

Improve → Experiment/Benchmark → Build/Environment → Compute → Governance（风险）→ Evidence detail。

## API capability required

已覆盖：
- POST /api/v1/runs
- GET /api/v1/runs/{run_id}
- GET /api/v1/operations/{operation_id}
- GET /api/v1/evidence/{evidence_id}

Contract Gap：
- **CG-04 Experiment/Reproduction create contract**
- **CG-05 UpstreamDependency snapshot/read contract**

## Third-party boundary

GitHub/paper source、package registry、MLflow 等只做 source/tracking；Experiment verdict 与 adoption Authority 属于平台。

## Needs Your Attention trigger

source revision 漂移、license 不兼容、dependency critical CVE、实验不可复现、结果显著但需要 Production adoption decision。

---

# Journey 04 — 创建 Knowledge / RAG Capability

| Field | Definition |
|---|---|
| Primary Actor | Data / Knowledge Engineer |
| Supporting Roles | AI Engineer、Application Developer、Security/Auditor |
| User Goal | 从受治理 KnowledgeAsset 构建可验证 RAG Capability，并允许业务通过统一 /v1 调用 |
| Entry Condition | source data 允许使用；embedding/retrieval/generation capability 可用 |
| Domain Objects | KnowledgeAsset、DatasetAsset、Index、Capability、EvaluationRun、Evidence、GateResult、Deployment |
| Exit Condition | RAG Capability 可调用，答案可返回 evidence/source refs，Index 可重建 |

## Main Flow

1. Data Engineer 创建 KnowledgeAsset，绑定 canonical sources 与 classification。
2. AI 执行解析、chunk、metadata/ontology 建议；人工处理来源冲突。
3. 平台选择 embedding/retrieval Adapter，构建 Index。
4. Index 记录 derivation lineage，不能成为 canonical Knowledge authority。
5. AI Engineer 组合 retrieval + generation 为 Capability spec。
6. 构造 Gold Set / EvaluationRun，验证 recall、groundedness、citation、latency、安全。
7. 通过 Gate 后在 staging 提供 /v1/responses 或 generic capability invocation。
8. Application Developer 做 integration；Production promotion 复用 Journey 06。

## AI actions

R0：index build/rebuild、chunk/profiling、retrieval test、evaluation、citation evidence。
R1：source conflict resolution suggestion、retrieval policy change proposal。
Sensitive external provider transfer 升级 R2。

## Human actions

Data owner 确认 canonical source 与 classification；AI Engineer 确认 Capability acceptance；Approver 处理 production/data transfer。

## R0/R1/R2/R3 transition

Index rebuild 是 R0；Knowledge canonical deletion 是 R2；外部 provider 处理敏感知识为 R2；最终 exception 可 R3。

## Evidence produced

source hashes、ingest lineage、Index build evidence、retrieval metrics、Gold Set results、citation/grounding evidence、Capability GateResult。

## Gate / Approval

Data classification、retrieval quality、grounding/citation、安全与 privacy Gate。

## Failure path / Retry / Rollback

Index 损坏直接 rebuild；canonical source 不回滚到 Index。新 retrieval config 回退时恢复上一 LKG Capability revision。

## UI screens touched

Knowledge → Knowledge Detail → Build → Experiment/Benchmark → AI Hub/Capability → Deployment。

## API capability required

已覆盖：
- PATCH /api/v1/capabilities/{capability_id}
- POST /api/v1/runs
- POST /v1/capabilities/{capability_id}:invoke
- POST /v1/responses
- POST /v1/embeddings

Contract Gap：
- **CG-06 KnowledgeAsset/Index build-rebuild action contract**

## Third-party boundary

Vector DB/Search Engine/Embedding Provider 都只能实现 Vector/Search/Provider Adapter；Index vendor collection ID 是 ExternalRef。

## Needs Your Attention trigger

source drift、index stale、citation/grounding Gate failed、sensitive source transfer request、retrieval backend unavailable。

---

# Journey 05 — GPU 高峰/低谷自动调度

| Field | Definition |
|---|---|
| Primary Actor | Operator / SRE |
| Supporting Roles | Platform Admin、AI Engineer、Researcher、Approver |
| User Goal | 在业务 SLA 优先下，让训练/评测自动利用低谷 GPU，并在高峰安全让出资源 |
| Entry Condition | Resource/GPU inventory 健康；Scheduler Policy 已批准；训练任务可 checkpoint/resume |
| Domain Objects | Resource、Node、GPU、Deployment、TrainingRun、EvaluationRun、Policy、Workflow、Evidence |
| Exit Condition | 高峰业务满足 SLA，低谷 batch 持续取得进展，公平/抢占/恢复可审计 |

## Main Flow

1. Compute 页面读取 GPU read model 与 active workload。
2. Scheduler 根据 frozen Policy 计算 service class、reservation、fair share、aging、training debt。
3. 低谷时自动把空闲资源分配给 batch/training/evaluation。
4. 负载升高时先 scale service，必要时请求训练 checkpoint。
5. checkpoint 验证完成后释放 GPU，再把服务扩到目标容量。
6. 高峰结束后恢复被抢占任务，记录 wait/debt。
7. SRE 只在 Policy 越界、反复恢复失败或预算风险时介入。

## AI actions

R0：forecast、placement、autoscale、checkpoint/resume（在已批准 Policy 内）、异常归因。
R1：修改 Scheduler Policy、扩大预算、改变优先级体系。

## Human actions

SRE/Platform Admin 冻结调度 Policy；Approver 批准生产级策略改变或全局预算扩大。

## R0/R1/R2/R3 transition

正常 placement/autoscale R0；Policy change R1→R2；紧急恢复可按预授权 incident Policy R0，否则 R2。

## Evidence produced

inventory snapshots、placement decisions、preemption reason、checkpoint hash、resume result、SLA metrics、training debt/fair-share、power/usage。

## Gate / Approval

Policy validation Gate、checkpoint recoverability、production SLA Gate。单次 placement 不逐次审批。

## Failure path / Retry / Rollback

checkpoint 失败则不得释放最后可恢复状态；服务扩容失败触发 LKG capacity policy；持续 starvation 触发 Attention。

## UI screens touched

Home → Compute/GPU → Run/Deployment → Training Run → Governance/Policy → Needs Your Attention。

## API capability required

已覆盖：
- GET /api/v1/resources/gpus
- GET /api/v1/operations/{operation_id}
- GET /api/v1/evidence/{evidence_id}

Contract Gap：
- **CG-07 Scheduler Policy read/mutate contract**
- **CG-08 checkpoint/preemption/resume action contract**

## Third-party boundary

NVIDIA telemetry、container runtime、libvirt、training backend 只提供 observation/action implementation；placement Authority 属于平台 Scheduler。

## Needs Your Attention trigger

SLA risk、GPU unhealthy、checkpoint unrecoverable、training starvation、budget/power threshold、scheduler policy conflict。

---

# Journey 06 — Candidate → Production

| Field | Definition |
|---|---|
| Primary Actor | AI Engineer / Service Owner |
| Supporting Roles | Approver、Operator/SRE、Security/Auditor |
| User Goal | 把已验证 Candidate 安全晋级 Production，失败时可快速恢复 LKG |
| Entry Condition | Candidate Deployment 存在；required GateResult 与 Evidence 完整；LKG 可定位 |
| Domain Objects | Deployment、Capability、GateResult、Approval、Evidence、Workflow、Policy |
| Exit Condition | Production status 由 Controller 确认，rollout Evidence 完整；或安全回滚到 LKG |

## Main Flow

1. Owner 打开 Deployment，比较 Candidate 与当前 Production/LKG。
2. AI 汇总 quality/perf/security/license/cost Evidence，生成 Decision Packet。
3. Control Hub 验证 gate_result_id、candidate revision、resource_version、rollout、rollback_lkg_ref。
4. 若 Gate failed，返回 GATE_BLOCKED；不能提交 force pass。
5. Gate pass 后生成 ApprovalRequirement。
6. Human Approver R3 决定 approve/reject。
7. 批准后系统 R2 执行 canary/progressive/blue-green rollout。
8. 每阶段观察 SLA/error budget；自动停止异常推进。
9. 全部通过后 Controller 更新 status=Production 并固化 Evidence。
10. 任何关键回退触发 LKG rollback。

## AI actions

R0：Evidence summary、risk detection、rollout observation。
R1：promotion recommendation。
R2：批准后执行 rollout。
禁止 self-approve、lower Gate、隐藏 failed Evidence。

## Human actions

Approver 做最终决定；SRE 在预授权边界外处理事故；Owner 确认业务窗口。

## R0/R1/R2/R3 transition

~~~text
Evidence synthesis R0
→ recommendation R1
→ approval decision R3
→ approved mutation R2
→ health observation R0
~~~

## Evidence produced

Decision Packet、GateResult、Approval、rollout stage evidence、traffic/error/SLA、final Production confirmation 或 rollback evidence。

## Gate / Approval

这是 Gate + Approval 的主参考旅程；任何 Production Promotion 都必须满足两者。

## Failure path / Retry / Rollback

412 版本冲突要求重新读当前资源；rollout failure 自动暂停；只有新 Evidence/新 Approval 可重新推进；LKG rollback 不删除 failed candidate。

## UI screens touched

Deployment → Experiment/Benchmark/Evidence → Approval Inbox → Run → Home/Attention。

## API capability required

完整覆盖：
- POST /api/v1/deployments/{deployment_id}:promote
- GET /api/v1/operations/{operation_id}
- GET /api/v1/evidence/{evidence_id}
- POST /api/v1/approvals/{approval_id}:decide

无新的 P1-02 Contract Gap。

## Third-party boundary

Serving backend 只能执行 rollout primitives；Production Authority、Gate、Approval 与 LKG 均在 Control Hub。

## Needs Your Attention trigger

Approval pending/expiring、Gate blocked、resource_version conflict、canary regression、rollback initiated、LKG 不可验证。

---

# Journey 07 — 第三方 Backend 替换

| Field | Definition |
|---|---|
| Primary Actor | Platform Admin |
| Supporting Roles | AI Engineer、SRE、Security/Auditor、Approver |
| User Goal | 用新 Backend 替换现有实现，不改变 Northbound Contract、Domain ID 与业务调用方式 |
| Entry Condition | Replacement Adapter candidate 可用；旧 Backend 仍可作为 LKG；数据/配置可导出 |
| Domain Objects | Adapter、Provider/Runtime、Deployment、Capability、UpstreamDependency、Evidence、GateResult、Approval |
| Exit Condition | 新 Backend 通过 conformance 和 production cutover，旧 Backend 可退役或保留 rollback window |

## Main Flow

1. Admin 创建 replacement candidate，明确被替换的 Adapter implementation 与 Exit Path。
2. 系统运行 Adapter conformance：request/response/error/usage/health + object-specific actions。
3. 导出/重建必要数据，不复制第三方内部 Authority。
4. 在 sandbox/staging 创建 parallel implementation。
5. 用相同 Capability/Run test corpus 做 A/B 或 shadow。
6. AI 汇总差异：quality、latency、cost、failure、migration risk。
7. Production cutover 生成 ApprovalRequirement。
8. Human 批准后执行分阶段流量切换。
9. 验证 northbound responses 与 Domain status；stable Capability/Deployment ID 不变。
10. 旧 Backend 在 rollback window 后按 policy retire。

## AI actions

R0：conformance、migration plan draft、shadow test、evidence diff。
R1：cutover recommendation。
R2：批准后的数据迁移/traffic switch。

## Human actions

Admin 确认 replacement intent；Security 检查新 dependency；Approver 决定 Production cutover。

## R0/R1/R2/R3 transition

non-prod conformance R0 → cutover proposal R1 → approval R3 → cutover R2 → observe R0。

## Evidence produced

Adapter conformance report、data portability proof、before/after metrics、ExternalRef mapping、cutover/rollback evidence。

## Gate / Approval

Conformance Gate、Data Portability Gate、Security/License Gate、Production cutover Approval。

## Failure path / Retry / Rollback

新 Backend 失败即切回旧 LKG；stable Domain ID 不变；ExternalRef 标记失效/恢复，不 rewrite history。

## UI screens touched

Govern → Dependencies/Adapters → AI Hub/Provider → Experiment/Benchmark → Deployment → Approval Inbox。

## API capability required

已覆盖：
- POST /api/v1/providers
- POST /api/v1/runs
- POST /api/v1/deployments/{deployment_id}:promote
- Approval/Operation/Evidence

Contract Gap：
- **CG-09 Adapter conformance / backend replacement action contract**
- **CG-10 ExternalRef migration mapping read model**

## Third-party boundary

整个旅程就是 boundary drill：Backend 不得要求 UI/API 改为 vendor DTO，不得占有 stable ID。

## Needs Your Attention trigger

conformance failure、data export gap、license/security regression、shadow mismatch、cutover error、rollback failure。

---

# Journey 08 — License 风险触发迁移

| Field | Definition |
|---|---|
| Primary Actor | Security / Auditor |
| Supporting Roles | Platform Admin、AI Engineer、Approver、业务 Owner |
| User Goal | 当依赖 License 风险变化时，定位影响面、阻断新增风险并迁移到可接受替代 |
| Entry Condition | UpstreamDependency 有 revision/license evidence；replacement register 可查询 |
| Domain Objects | UpstreamDependency、Adapter、Artifact、Deployment、Capability、Policy、Evidence、Approval |
| Exit Condition | 风险依赖被隔离/替换，或由授权人留下有期限、可审计的 R3 override decision |

## Main Flow

1. dependency scan 发现 license change / incompatibility / unknown evidence。
2. 平台把 Dependency Risk 标为 NEEDS_REVIEW/BLOCKED，并计算受影响 Artifact/Deployment/Capability lineage。
3. AI 生成 migration options、replacement candidates、cost/compatibility comparison。
4. 默认策略阻断新 Promotion/新 build 使用高风险 revision。
5. Admin/AI Engineer 在非生产验证 replacement。
6. 通过 conformance 后进入 Journey 07 cutover。
7. 如果业务要求暂缓迁移，只有授权 human 可以做 time-bounded R3 License Override。
8. override 到期前持续进入 Needs Your Attention；不能永久静默豁免。

## AI actions

R0：detect、impact graph、replacement research、migration plan。
R1：recommend migration/temporary mitigation。
不能做最终 License Override。

## Human actions

Security/Auditor 确认风险等级；Approver/legal governance 做 R3 override decision；Owner 选择业务窗口。

## R0/R1/R2/R3 transition

detect R0 → mitigation/migration proposal R1 → cutover R2 after approval；license override final decision R3。

## Evidence produced

old/new license hash、dependency revision、impact lineage、replacement evaluation、override decision、migration/cutover evidence。

## Gate / Approval

License Gate 默认 fail closed；override 不等于修改 Gate，而是独立 governance decision 且有期限。

## Failure path / Retry / Rollback

replacement 不合格则继续阻断或保留当前 LKG；不允许删除原 License Evidence。override 到期未解决触发更高 Attention。

## UI screens touched

Home/Attention → Govern/Dependencies → Adapter/Provider detail → Experiment → Deployment → Approval Inbox。

## API capability required

Contract Gap：
- **CG-11 UpstreamDependency risk/status API**
- **CG-12 time-bounded governance exception contract**

复用 Operation/Evidence/Approval common contract。

## Third-party boundary

upstream repo/license source 是 Evidence 来源，不是平台 risk decision Authority。

## Needs Your Attention trigger

critical license risk、新 Promotion 被阻断、override 即将到期、replacement 无可用候选、cutover 失败。

---

# Journey 09 — Agent 自动执行 + Human Approval

| Field | Definition |
|---|---|
| Primary Actor | 任一授权用户；示例 AI Engineer |
| Supporting Roles | Approver、SRE、Security/Auditor |
| User Goal | 让 AI Operator 自动完成可授权步骤，但在高风险动作前生成清晰 Decision Packet 并等待人类审批 |
| Entry Condition | Current Principal/Project/Environment/Policy 已解析；Agent 有受控 Tool/API access |
| Domain Objects | Agent、Principal、Project、Workflow、Approval、Policy、Evidence、Capability/Deployment/Run |
| Exit Condition | 任务完成且所有动作可追溯；或在越权边界前安全停止并进入 Attention |

## Main Flow

1. 用户在 AI Operator 输入目标，例如“把 candidate X 推到 production，但失败自动回 LKG”。
2. Operator 显示 Acting as、Scope、Environment、Responsibility Level。
3. AI 生成 plan，并把每步标为 R0/R1/R2/R3。
4. R0 read/probe/test 自动执行并持续收集 Evidence。
5. 到 Production Promotion 时生成 Decision Packet，而不是直接调用 backend。
6. Approval Inbox 显示 proposed action、side effects、Gate、Evidence destination、rollback/LKG。
7. Human Approver R3 决定。
8. 批准后 Operator 调用同一 Northbound API 执行 R2 action。
9. 完成后 post-condition verification；结果写 Evidence。
10. 拒绝/超时则 Workflow 停在明确状态，不自行换身份重试。

## AI actions

R0：计划、read、probe、test、summarize、request approval。
R1：建议 high-risk change。
R2：仅执行已批准动作。
禁止 self-approve、self-escalate、plaintext secret prompt、backend side channel。

## Human actions

用户定义目标；Approver 做最终决定；必要时 Security/SRE 接管异常。

## R0/R1/R2/R3 transition

这是责任模型的标准演示：
R0 自动步骤 → R1 建议 → R3 人决策 → R2 执行 → R0 验证。

## Evidence produced

effective Principal、scope、plan revision、tool/API calls、Decision Packet、Approval、execution result、post-check、failure/rollback。

## Gate / Approval

Operator 不能绕过 Gate；Command Palette 也使用同一 API/Policy。

## Failure path / Retry / Rollback

R0 步骤可 bounded retry；越 retry/budget 转 Attention。Approval reject/expire 后不执行。R2 action 失败按其 Domain rollback policy。

## UI screens touched

AI Operator（全程）→ Needs Your Attention / Approval Inbox → 对应 Domain Detail → Evidence。

## API capability required

复用所有现有 Northbound common contract，尤其：
- X-Correlation-ID
- Idempotency-Key
- OperationReference
- ErrorEnvelope / ApprovalRequirement / GateBlock
- Approval decision
- Capability invocation

Contract Gap：
- **CG-13 Agent execution context / Decision Packet read model**，应在 P1-03 Event/P1-04 State Machine 前冻结字段，而不是创建 AI 专用后门 API。

## Third-party boundary

Agent 只能调用平台 Tool/Northbound API；禁止直接使用 backend admin API 获得额外能力。

## Needs Your Attention trigger

Approval required、permission/policy denied、retry budget exhausted、unexpected side effect、secret request、Gate blocked、scope ambiguity。

---

# Journey 10 — 故障恢复至 LKG

| Field | Definition |
|---|---|
| Primary Actor | Operator / SRE |
| Supporting Roles | Platform Admin、AI Engineer、Approver |
| User Goal | 生产故障时恢复到已验证 LKG，并保留完整事故与恢复 Evidence |
| Entry Condition | LKG reference 可定位；incident/recovery Policy 已冻结；至少有一种可执行恢复路径 |
| Domain Objects | Deployment、Capability、Artifact、Environment、Workflow、Evidence、GateResult、Policy、Resource |
| Exit Condition | 服务恢复到 verified LKG 或明确进入 degraded/manual escalation；事故 Evidence 完整 |

## Main Flow

1. Observability 发现 availability/error/latency regression。
2. 平台关联最近 mutation/deployment/backend/resource change。
3. AI/SRE 确认当前 Production 与 LKG 差异。
4. 若预授权 incident Policy 允许，系统 R0 执行 bounded rollback；否则生成 R2 ApprovalRequirement。
5. ServingAdapter 恢复 LKG artifact/config/implementation。
6. Control Hub 重新 probe Capability、health、traffic 与关键业务 smoke。
7. 成功后 status=RECOVERED/PRODUCTION-LKG，并记录 incident evidence。
8. 原失败 candidate 标记 FAILED/DEGRADED，保留，不覆盖。
9. 后续 root-cause fix 走新的 Candidate/Evaluation，不直接修生产历史。

## AI actions

R0：incident correlation、LKG lookup、health probe、预授权 rollback、post-check。
R1：超出预授权边界的恢复建议。
不得把未通过 Gate 的临时版本标为 LKG。

## Human actions

SRE 在 blast radius/unknown state 时确认恢复；Approver 处理未预授权 production mutation；AI Engineer 后续修复 candidate。

## R0/R1/R2/R3 transition

pre-authorized incident rollback 可 R0；未授权 production change 是 R2；修改 recovery policy 是 R1→R2；重大 exception 可 R3。

## Evidence produced

incident start、symptoms、correlation、selected LKG reason、rollback operation、health/smoke、traffic recovery、failed candidate refs、postmortem refs。

## Gate / Approval

Recovery Gate 关注 LKG validity、artifact integrity、environment compatibility、post-restore health。紧急策略不能关闭 audit。

## Failure path / Retry / Rollback

LKG 恢复失败时按预定义 fallback chain 尝试下一 verified LKG/implementation；超过 retry/blast radius 转人工 incident escalation。

## UI screens touched

Home/Attention → Run/Deployment → Compute → Evidence/Incident detail → AI Operator。

## API capability required

已覆盖 common Operation/Evidence/GPU read。

Contract Gap：
- **CG-14 Deployment recover-to-LKG action contract**
- **CG-15 incident/recovery read model**

## Third-party boundary

Serving/VM/container backend 只执行恢复 primitives；哪个版本是 LKG、何时触发 rollback、恢复是否完成由 Control Hub + Evidence 决定。

## Needs Your Attention trigger

production unhealthy、automatic rollback started/failed、LKG invalid、fallback exhausted、unknown blast radius、manual approval needed。

---

# 11. Contract Gap Register

Golden Journeys 对 WP-P1-02 baseline 的反向审计结果如下。

| Gap | Needed by | Contract need | Owner WP | Priority |
|---|---|---|---|---|
| CG-01 | J01 | ModelAsset intake action family | P1-02 extension + P1-05 | P1 |
| CG-02 | J02 | DatasetAsset intake/revision | P1-02 extension | P1 |
| CG-03 | J02 | checkpoint/resume action semantics | P1-04 + P1-05 | P1 |
| CG-04 | J03 | Experiment/Reproduction create | P1-02 extension | P1 |
| CG-05 | J03 | UpstreamDependency snapshot/read | P1-02/P1-03 | P1 |
| CG-06 | J04 | KnowledgeAsset/Index build-rebuild | P1-02 + P1-05 | P1 |
| CG-07 | J05 | Scheduler Policy read/mutate | P1-02 + P1-04 | P1 |
| CG-08 | J05 | checkpoint/preemption/resume orchestration | P1-04 | P1 |
| CG-09 | J07 | Adapter conformance/backend replacement action | P1-05 | P1 |
| CG-10 | J07 | ExternalRef migration mapping read model | P1-02/P1-05 | P2 |
| CG-11 | J08 | UpstreamDependency risk/status API | P1-02/P1-04 | P1 |
| CG-12 | J08 | time-bounded governance exception | P1-02/P1-04 | P1 |
| CG-13 | J09 | Agent execution context / Decision Packet read model | P1-03/P1-04 | P1 |
| CG-14 | J10 | recover-to-LKG action | P1-02/P1-04 | P1 |
| CG-15 | J10 | incident/recovery read model | P1-02/P1-03 | P2 |

判定：

- 这些 Gap **不推翻 WP-P1-02 common contract**。
- 不应为了清零 Gap 一次性增加几十个 CRUD endpoint。
- P1-03 Event、P1-04 State Machine、P1-05 Adapter Contract 必须优先吸收 action/state 语义。
- 对 UI 立即必需的 endpoint family，在进入 P3 前补齐 OpenAPI。

# 12. Orphan API Risk Audit

当前 WP-P1-02 baseline operation 均被至少一个 Journey 消费：

| Operation family | Journey |
|---|---|
| Capability invoke | J04、J09 |
| /v1/chat/completions | J01 |
| /v1/responses | J01、J04 |
| /v1/embeddings | J04 |
| Capability list/get/patch | J04、AI Hub browse flow |
| Deployment promote | J01、J06、J07 |
| Run create/get | J01、J02、J03、J04、J07 |
| GPU read model | J02、J05、J10 |
| Operation query | 所有 long-running Journey |
| Evidence read | 全部 Journey |
| Approval decide | J01、J06、J07、J09 |
| Provider onboarding | J01、J07 |

**Orphan API Risk：NONE at baseline。**

注意：Capability list/get 属于 IA 级 browse prerequisite，不需要人为制造独立 Journey。

# 13. Journey → 一级导航输入

| Journey | Primary nav | Secondary nav |
|---|---|---|
| J01 外部模型上线 | AI Hub | Build / Improve / Run / Govern |
| J02 Dataset→Train | Build | Improve / Compute / AI Hub |
| J03 Research Reproduction | Improve | Build / Compute / Govern |
| J04 Knowledge/RAG | Knowledge | Build / Improve / AI Hub |
| J05 GPU 自动调度 | Compute | Run / Govern / Home |
| J06 Candidate→Production | Run | Improve / Govern / Home |
| J07 Backend Replacement | Govern | AI Hub / Improve / Run |
| J08 License Migration | Govern | Home / Improve / Run |
| J09 Agent + Approval | AI Operator global | Govern / affected domain |
| J10 Recover to LKG | Run / Home | Compute / Govern / AI Operator |

该映射是 WP-P2-04 Information Architecture 的直接输入。

# 14. Acceptance Criteria

- [x] 十条 Journey 全部覆盖 Primary Actor / Supporting Roles / Goal / Entry / Domain Objects / Flow / AI / Human / R0-R3 / Evidence / Gate / Approval / Failure / Retry / Rollback/LKG / Exit / UI / API / Third-party / Attention。
- [x] Journey 不绑定 Qwen、vLLM、SGLang 或 4090。
- [x] AI Operator 没有超级用户后门。
- [x] Production、License、Security、Backend cutover 均体现 Human Authority。
- [x] 识别 15 个 Contract Gap，并分配到后续 P1 WP。
- [x] 对现有 API 做 Orphan Risk 审计，无 baseline orphan。
- [x] 已形成 P2-04 IA 的任务路径输入。

# 15. Exit Condition

WP-P2-03 完成。下一步直接进入 WP-P2-04 Information Architecture；P1 Contract Gap 保持显式，不阻塞 IA/Low-fi，但在 P3 Repository Skeleton 前必须有 owner 与收敛顺序。

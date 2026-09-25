# Low-fi Wireframes v1.0

> Work Package：**WP-P2-05 Low-fi Wireframes**
>
> 状态：**Task-flow Baseline**
>
> 目标：确认信息层级、任务路径、Authority、Evidence、Gate、Approval 与异常状态；**不追求视觉成品，不冻结颜色、字体或品牌风格。**
>
> 输入：Roles、Human-AI Responsibility、Golden Journeys、Information Architecture、Northbound API Boundary。

# 1. 全局 Wireframe Grammar

所有核心页面共享以下 App Shell：

~~~text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Project ▾ | Environment ▾ | Acting as: Principal | Search | Attention (n)  │
│ Home | AI Hub | Build | Run | Improve | Knowledge | Compute | Govern       │
│                                                AI Operator | Notify | ⌘K    │
└──────────────────────────────────────────────────────────────────────────────┘
│ Breadcrumb / Stable Domain ID / resource_version                            │
│ Page title + lifecycle/status + scope + owner                               │
│                                                                              │
│ Main task area                                      Context / Evidence rail   │
│                                                      Gate / Approval / AI     │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## 1.1 全局 Authority strip

任何存在真实副作用动作的页面，在 action 区附近必须可见：

- Acting as；
- Project Scope；
- Environment；
- Responsibility Level；
- resource_version / concurrency state；
- Gate state；
- Approval state；
- rollback/LKG（适用时）。

不能只在 AI Operator 中显示。

## 1.2 Status vocabulary

第一轮视觉语义必须区分：

- Candidate
- Production
- Failed
- LKG
- Pending / Running / Blocked
- Degraded / Unavailable
- Archived / Superseded

Candidate 与 Production 不得只靠颜色区别。

LKG 是独立标识，允许与当前 Production 指向同一 revision，也允许在 incident 后显示“Recovered to LKG”。

## 1.3 spec vs status

所有详情页至少提供两个明确区域：

~~~text
Declared / Spec
Observed / Status
~~~

禁止把 backend observation 写进 spec，也禁止把 desired config 当实际运行状态展示。

## 1.4 Evidence / Gate / Approval rail

右侧 Context Rail 统一顺序：

1. Status summary
2. Evidence
3. Gate
4. Approval
5. External implementation details
6. Audit / recent changes

External implementation detail 永远排在 Domain state 之后，且明确标记“Implementation / ExternalRef”。

## 1.5 AI suggestion vs execution

UI action 文案必须明确区分：

- **Ask AI / Analyze**：R0 read/analysis；
- **Generate proposal**：R1；
- **Execute**：R0 bounded mutation；
- **Request approval**：进入 R2；
- **Approve / Reject**：R3 human-only decision。

不得用单一“Run”按钮混淆 suggestion 与 mutation。

## 1.6 通用异常状态

每页都必须区分：

- Empty：确实没有对象；
- Loading：等待 authoritative read；
- Error：平台请求失败；
- Partial Failure：主对象可读，但某些 observation/evidence/backend 不可读；
- Backend Unavailable：第三方实现不可用，但 Domain Authority 仍可读；
- Permission Denied：用户身份/Policy 不允许动作或对象访问。

Backend Unavailable 不等于 Domain Not Found。

# 2. Home

## Page Goal

快速回答“平台是否健康、我现在需要处理什么、哪些长任务/风险影响当前 Project”。

**Primary Role：** Operator/SRE；同时服务 Admin、Approver、Security、AI Engineer。

## Information hierarchy

1. Needs Your Attention；
2. Production Capability health；
3. Active Operations；
4. Compute pressure；
5. Pending Approval / Gate blocked；
6. Dependency/license/security；
7. Recent significant changes。

## Low-fi

~~~text
┌ Home ───────────────────────────────────────────────────────────────────────┐
│ ATTENTION  [3 urgent]  [View all]                                          │
│ ┌ Gate blocked: deployment_x ┐ ┌ Approval pending: promote_y ┐             │
│ └────────────────────────────┘ └───────────────────────────────┘             │
│ Production health       Active operations        Compute pressure            │
│ 12 healthy / 1 degraded  4 running / 1 blocked   GPU 82% / queue 7          │
│                                                                              │
│ Recent significant changes                                                   │
│ time | object | action | actor | evidence                                   │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- Open Attention item；
- open degraded Capability/Deployment；
- inspect Operation；
- ask AI to summarize today’s risks。

## Dangerous actions

Home 不直接提供 promote/delete/reboot。所有危险动作必须进入对象详情并重新显示 Authority context。

## Status / Evidence / Approval

聚合状态是 read model；点击后回 canonical object。Evidence 只显示摘要。Approval card 只跳 Inbox，不在 Home 一键批。

## AI distinction

“Summarize / Diagnose” 是 R0；“Fix” 只能生成 proposal 或进入对应对象 action。

## Edge states

- Empty：显示“当前无 Attention / 无活跃任务”，不是空白页。
- Loading：保留 Shell 和 last-known timestamp，占位卡显示正在刷新。
- Error：平台聚合失败，给 retry；不把所有对象标红。
- Partial Failure：逐卡标记 stale/unknown，并显示 last observed_at。
- Backend unavailable：只影响对应 capability/telemetry card，Domain summary 仍可用。
- Permission denied：隐藏无权读取的敏感聚合，并解释所需 Role。

---

# 3. AI Hub

## Page Goal

从 Capability 开始发现“平台能做什么”，再下钻 Model/Provider/Deployment implementation。

**Primary Role：** AI Engineer；Application Developer 为 read/use 重点角色。

## Information hierarchy

1. Capability catalog；
2. filters：modality/status/environment/owner；
3. production readiness；
4. model/provider implementation count；
5. Gate/Evidence health；
6. recent candidate changes。

## Low-fi

~~~text
┌ AI Hub ─────────────────────────────────────────────────────────────────────┐
│ [Capabilities] [Models] [Providers]                     [+ Add candidate]   │
│ Search...  Modality ▾  Status ▾  Environment ▾                              │
│ Capability          Status       Production     Candidate     Evidence       │
│ coding              Healthy      dep_prod_1     dep_can_3     Gate PASS      │
│ vision              Degraded     dep_prod_2     —             2 alerts       │
│ meeting-assistant   Candidate    —              dep_can_9     Review         │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- browse/search Capability；
- add model/provider candidate；
- compare implementations；
- invoke in playground via /v1；
- open Model/Deployment details。

## Dangerous actions

Add candidate 是低风险；Production Promotion 不在 catalog row 内直接执行。

## Status / Evidence / Approval

每行同时显示 stable Capability status 与 production/candidate relation。External provider status 是次级信息。

## AI distinction

AI 可推荐“哪一个 implementation 更适合”，但 recommendation 与 “Set Production” 分开。

## Edge states

- Empty：提示先创建/import Capability candidate。
- Loading：表骨架 + filter 保持。
- Error：catalog read error，保留 Search/Scope。
- Partial Failure：implementation telemetry 不可用时 Capability 仍可显示。
- Backend unavailable：对应 implementation 标记 unavailable，不删除 Capability。
- Permission denied：read-only 用户可见 catalog，创建/修改动作禁用并说明。

---

# 4. Model Detail

## Page Goal

理解一个 ModelAsset 的来源、business revision、能力证据、候选部署与外部映射。

**Primary Role：** AI Engineer。

## Information hierarchy

1. Stable ModelAsset ID + business revision；
2. Spec / Status；
3. source/provenance/license；
4. Capability mapping；
5. Evaluation evidence；
6. Candidate/Production deployments；
7. ExternalRef。

## Low-fi

~~~text
┌ Model: model_x / rev 7 ─────────────────────────────────────────────────────┐
│ Status: Candidate-ready | Owner | Scope | resource_version 14              │
│ [Spec] base/source/revision/hash       [Status] validated / observed_at     │
│                                                                              │
│ Capabilities          Evaluation summary          Deployments                │
│ coding ✓              quality 0.91 PASS           can_3 Candidate            │
│ reasoning ✓           safety PASS                 prod_1 Production / LKG    │
│                                                                              │
│ Evidence / Gate / Approval                                     [Context]     │
│ External implementation: ModelScope ref..., artifact digest...               │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- create new business revision；
- run evaluation；
- create candidate deployment；
- compare revisions；
- open source/license evidence。

## Dangerous actions

Retire published revision、external publish、delete canonical asset 都必须 R2；Production promotion 从 Deployment page 执行。

## Status / Evidence / Approval

Business revision 与 resource_version 必须并列但明确不同。Gate 按 revision 显示，不能让旧 PASS 自动覆盖新 revision。

## AI distinction

“Suggest evaluation / deployment profile” 是 R1；创建 non-prod candidate 可 R0；publish/promote 进入 approval。

## Edge states

- Empty：新资产无 evaluation 时显示 onboarding checklist。
- Loading：先显示 stable identity，再加载 evidence/implementation。
- Error：ModelAsset read 失败显示错误，不展示 backend-only detail 替代。
- Partial Failure：source/provider status unknown 时 canonical metadata 仍可读。
- Backend unavailable：ExternalRef 卡片 degraded，不改变 ModelAsset ID。
- Permission denied：license/security detail按权限裁剪，mutation 禁用。

---

# 5. Dataset Detail

## Page Goal

确认 DatasetAsset 的来源、classification、business revision、质量、lineage 与训练用途。

**Primary Role：** Data / Knowledge Engineer。

## Information hierarchy

1. Dataset stable ID / revision / classification；
2. Spec / Status；
3. provenance/license/consent；
4. profile/quality/dedupe；
5. lineage / downstream runs；
6. Evidence/Gate；
7. storage ExternalRef。

## Low-fi

~~~text
┌ Dataset: dataset_x / rev 12 ────────────────────────────────────────────────┐
│ Classification: Internal | Status: Ready | Gate: PASS                      │
│ [Spec] sources / purpose / revision      [Status] rows/files/hash          │
│ Quality  Missing  Duplicates  Sensitive findings                           │
│ 0.96     0.2%     1.1%        0 unresolved                                │
│ Used by: trainingrun_a, knowledge_b                                         │
│ Evidence: provenance | license | profile | review                           │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- import new revision；
- profile/dedupe；
- change classification proposal；
- create TrainingRun；
- view lineage。

## Dangerous actions

classification downgrade、sensitive export、canonical delete 是 R2/R3 policy path。

## Status / Evidence / Approval

Quarantine / Ready / Blocked / Superseded 必须可见。Approval 卡显示 classification/export decision。

## AI distinction

AI 可提出 classification/quality 建议，但不能静默降低敏感级别。

## Edge states

- Empty：新 Dataset 无文件时展示 import/source action。
- Loading：identity/classification 优先加载。
- Error：canonical read error。
- Partial Failure：profiling job 失败时 Status 标 partial，source 仍可读。
- Backend unavailable：Object Storage/Source backend unavailable 单独标记。
- Permission denied：敏感 sample/profile 可隐藏，但保留“restricted”说明。

---

# 6. Training Run

## Page Goal

观察 TrainingRun 从 queued → running → checkpoint/resume → complete/failed 的真实过程和资源证据。

**Primary Role：** AI Engineer。

## Information hierarchy

1. Run ID / spec revision / status；
2. progress + current phase；
3. pinned inputs；
4. GPU allocation；
5. metrics；
6. checkpoint/recovery；
7. Evidence / Operation / external job refs。

## Low-fi

~~~text
┌ Training Run: trainingrun_x ────────────────────────────────────────────────┐
│ RUNNING 42% | Operation op_7 | Workflow wf_9 | resource_version 8          │
│ [Spec] model rev / dataset rev / env / budget                              │
│ [Status] phase=train / observed_at / retry=1                               │
│                                                                              │
│ Metrics chart placeholder       GPU allocations                             │
│ loss / throughput               gpu_1 gpu_2 gpu_3 gpu_4                    │
│                                                                              │
│ Checkpoint: cp_18 VERIFIED  [Pause/Checkpoint]*                             │
│ Evidence timeline | backend job ref (external)                              │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- inspect metrics；
- bounded retry；
- checkpoint/pause/resume when Contract allows；
- cancel non-prod；
- open output ModelAsset/Evaluation。

## Dangerous actions

Kill without checkpoint、budget expansion、production resource override 需要提升责任等级。

## Status / Evidence / Approval

Queued/Running/Paused/Recovering/Succeeded/Failed/Cancelled 分离；checkpoint validity 显示 Evidence。

## AI distinction

AI 可建议“checkpoint now / reduce batch”等；只有 Policy 允许的自动动作才显示 Executed by system。

## Edge states

- Empty：不适用，Run detail 必须有对象；若不存在是 404。
- Loading：显示 Run identity + last status。
- Error：Control Hub read error。
- Partial Failure：metrics backend unavailable 时 run lifecycle 仍 authoritative。
- Backend unavailable：training backend lost 时显示 LOST/UNKNOWN observation，不伪造 Failed。
- Permission denied：敏感 logs/artifacts裁剪，允许基础 status 依 policy。

---

# 7. Deployment

## Page Goal

管理 Candidate / Production / Failed / LKG 生命周期，完成 Promotion、rollout、rollback 与恢复。

**Primary Role：** Operator/SRE + AI Engineer。

## Information hierarchy

1. lifecycle badge；
2. Capability / revision / environment；
3. Spec / Status；
4. Candidate vs Production vs LKG comparison；
5. health/SLA；
6. Gate；
7. Approval；
8. rollout/recovery；
9. External serving implementation。

## Low-fi

~~~text
┌ Deployment: deployment_x ──────────────────────────────────────────────────┐
│ CANDIDATE | target: Production | rv=21                                     │
│ Capability coding | model rev 7 | env Production                           │
│ [Spec] desired replicas / policy      [Status] ready 4/4 / health GREEN    │
│                                                                              │
│ Candidate rev 7      Production rev 6      LKG rev 6                       │
│ Quality PASS         SLA baseline          Verified 2026-09-24             │
│                                                                              │
│ Gate: PASS  Approval: REQUIRED   Rollback: LKG rev 6                       │
│ [Generate proposal] [Request approval] [Promote]*                           │
│ External: ServingAdapter/vLLM ref ... (not authority)                      │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- compare candidate vs production/LKG；
- generate promotion proposal；
- request approval；
- execute approved rollout；
- rollback/recover；
- inspect health/evidence。

## Dangerous actions

Promote、retire production、non-LKG force rollback 等必须显式 responsibility handling。

## Status / Evidence / Approval

本页是 Gate/Approval/LKG 的主参考页。Promotion 按钮在没有 Approval 时不得伪装可执行。

## AI distinction

“Recommend promote” 与 “Promote” 分开。AI recommendation 必须显示依据与不确定性。

## Edge states

- Empty：candidate 不存在时提供“Create candidate”路径；Production 可能为空。
- Loading：显示 stable Deployment ID 与上次状态。
- Error：Control Hub read error。
- Partial Failure：telemetry missing 时 status 标 unknown/degraded。
- Backend unavailable：Serving backend unavailable，但 spec/Gate/Approval/LKG 仍可读。
- Permission denied：read 可见；Promotion action 显示所需 Approver/Role。

---

# 8. Compute / GPU

## Page Goal

查看 Node/GPU 健康、利用率、分配、训练债与服务压力，并进行受控运维。

**Primary Role：** Operator/SRE。

## Information hierarchy

1. fleet summary；
2. health/temperature/power；
3. allocation；
4. active workload；
5. reservation / queue / training debt；
6. node topology；
7. evidence / maintenance state。

## Low-fi

~~~text
┌ Compute / GPU ──────────────────────────────────────────────────────────────┐
│ Healthy 7/8 | Allocated 6 | Queue 4 | Production pressure HIGH             │
│ GPU      Health   VRAM       Util  Workload          Allocation             │
│ gpu_1    OK       21/24G     92%   deployment_a     production              │
│ gpu_2    OK       19/24G     81%   trainingrun_b    batch                   │
│ gpu_7    WARN     2/24G      10%   —                drain pending           │
│                                                                              │
│ [Ask AI capacity plan] [Open scheduling policy]                             │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- filter Node/GPU；
- open active workload；
- ask capacity diagnosis；
- drain/reboot where Policy allows；
- inspect scheduler decision evidence。

## Dangerous actions

production drain/reboot、global scheduling policy、budget/power override。

## Status / Evidence / Approval

Telemetry 是 observed status，必须显示 observed_at。Allocation decision 可点开 Evidence。

## AI distinction

AI capacity plan 是 proposal；actual drain/reboot 清楚标记责任等级和 blast radius。

## Edge states

- Empty：没有注册 Resource 时显示 onboarding，不显示 0% 假 telemetry。
- Loading：保留 last observed snapshot。
- Error：inventory API error。
- Partial Failure：单节点 telemetry 缺失只影响该节点。
- Backend unavailable：libvirt/NVIDIA exporter failure 单独标记，不删除 GPU Domain Object。
- Permission denied：Viewer 看只读；maintenance controls hidden/disabled。

---

# 9. Experiment / Benchmark

## Page Goal

比较 baseline/candidate，确认实验是否可复现、Gate 为什么 PASS/FAIL，以及下一轮该做什么。

**Primary Role：** Researcher / AI Engineer。

## Information hierarchy

1. Experiment goal / hypothesis；
2. pinned revisions；
3. status/reproducibility；
4. metrics/Pareto；
5. baseline comparison；
6. Evidence；
7. GateResult；
8. AI analysis / next experiment proposal。

## Low-fi

~~~text
┌ Experiment: experiment_x ──────────────────────────────────────────────────┐
│ COMPLETE | Reproducible YES | Gate PARTIAL                                 │
│ Hypothesis: ...                                                             │
│ Baseline rev 5    Candidate rev 7                                           │
│ Metric          Base      Cand      Δ       Gate                            │
│ quality         .88       .91       +.03    PASS                            │
│ p95 latency     420ms     470ms     +50ms   FAIL                            │
│ power           2.1kW     1.9kW     -0.2    PASS                            │
│                                                                              │
│ Evidence timeline | [Ask AI analyze] [Create next experiment proposal]      │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- view/compare runs；
- inspect raw/summary Evidence；
- create follow-up experiment；
- export report reference；
- open candidate asset。

## Dangerous actions

改 Gate threshold 以获得 PASS、删除 failed evidence、把 incompatible benchmark 合并。

## Status / Evidence / Approval

GateResult 明确按每个 check 展示。Failed experiment 是有效 Evidence，不是 Error UI。

## AI distinction

AI 可提出原因与下一轮实验，不能更改 frozen acceptance。

## Edge states

- Empty：无 runs 时展示“尚未执行”。
- Loading：显示 hypothesis/pinned inputs。
- Error：Experiment object read error。
- Partial Failure：某 metric collector 失败，标 missing，不填 0。
- Backend unavailable：tracking backend failure 不影响已落平台 Evidence。
- Permission denied：sensitive benchmark inputs 隐藏但 verdict 依 policy 可见。

---

# 10. Knowledge

## Page Goal

管理 KnowledgeAsset、source lineage、Index 派生状态、retrieval quality 与 RAG Capability 关系。

**Primary Role：** Data / Knowledge Engineer。

## Information hierarchy

1. KnowledgeAsset canonical sources；
2. classification / freshness；
3. Index derivation；
4. retrieval evaluation；
5. connected Capability；
6. Evidence / policy；
7. backend implementation detail。

## Low-fi

~~~text
┌ Knowledge ──────────────────────────────────────────────────────────────────┐
│ Asset: knowledge_x | READY | Sources 128 | Last sync 2h                    │
│ Canonical sources                Derived indexes                            │
│ source_a VERIFIED               index_vec_3 HEALTHY                         │
│ source_b STALE                  index_search_7 REBUILDING                    │
│                                                                              │
│ Retrieval quality 0.93 PASS | Citation 0.97 PASS                            │
│ RAG Capability: capability_rag_1                                             │
│ [Rebuild index] [Run evaluation] [Ask AI source-gap analysis]               │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- inspect/add canonical source；
- rebuild Index；
- run retrieval evaluation；
- open RAG Capability；
- review source drift。

## Dangerous actions

delete canonical source、classification downgrade、external sensitive transfer。

## Status / Evidence / Approval

Index status 与 KnowledgeAsset status 分开；Index failure 不能显示 Knowledge Lost。

## AI distinction

AI 可发现 source gaps / propose ingestion；canonical source acceptance按 data policy。

## Edge states

- Empty：没有 KnowledgeAsset 时提供 create/import。
- Loading：先显示 canonical identity。
- Error：Control Hub read error。
- Partial Failure：Index backend down 时 canonical source 仍可读。
- Backend unavailable：Vector/Search Adapter card 标 unavailable，可发起 rebuild/failover proposal。
- Permission denied：受限 source 内容隐藏，metadata按 policy 展示。

---

# 11. Governance

## Page Goal

统一查看 Policy、Gate、Dependency risk、Adapter/Provider、Access 与 Audit，而不是提供后台万能开关。

**Primary Role：** Platform Admin / Security-Auditor。

## Information hierarchy

1. urgent governance Attention；
2. approvals summary；
3. policy/gate status；
4. dependency/license risk；
5. adapter/provider conformance；
6. access/principal；
7. audit/evidence。

## Low-fi

~~~text
┌ Govern ─────────────────────────────────────────────────────────────────────┐
│ Attention: 2 critical | Approvals: 4 | Policy drift: 0                     │
│ [Approvals] [Policies] [Gates] [Dependencies] [Adapters] [Access] [Audit]  │
│                                                                              │
│ Critical risks                                                               │
│ dep_x  LICENSE_CHANGED   blocks 3 deployments     [Review]                  │
│ adapter_y CONFORMANCE_FAIL                       [Evidence]                  │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- open risk；
- review policy/gate；
- inspect dependency/adapter；
- manage ordinary access via approval flow；
- open audit trail。

## Dangerous actions

policy change、privileged grant、license/security exception、destructive delete。

## Status / Evidence / Approval

每个 policy/gate/dependency 变化都需要 version/evidence。没有 “disable audit” action。

## AI distinction

AI 可生成 risk summary/Decision Packet；final security/license/approval decision 是 Human。

## Edge states

- Empty：无风险时显示 healthy governance，不隐藏当前 policy版本。
- Loading：保留 tabs 与 last refresh。
- Error：governance API error 明确。
- Partial Failure：dependency scanner down 不等于“无风险”，显示 UNKNOWN。
- Backend unavailable：IdP/registry/provider backend 分项 degraded。
- Permission denied：普通用户只看允许的 Gate/Evidence，治理 mutation 不可见。

---

# 12. Approval Inbox

## Page Goal

让授权人基于完整 Decision Packet 做最终 Human decision，不被 AI recommendation 代替。

**Primary Role：** Approver。

## Information hierarchy

1. pending/expiring/high-risk queue；
2. action + affected object；
3. requester / Acting as；
4. scope/environment；
5. R-level；
6. Gate；
7. Evidence；
8. side effects；
9. rollback/LKG；
10. approve/reject reason。

## Low-fi

~~~text
┌ Approval Inbox ─────────────────────────────────────────────────────────────┐
│ Pending 4 | Expiring 1 | High risk 2                                       │
│ ┌ Promote deployment_x → Production ────────────────────────────────────┐  │
│ │ Requested by principal_a / Agent wf_9 | R2 action                      │  │
│ │ Gate PASS | Evidence 12 | LKG deployment_old                          │  │
│ │ Side effects: traffic shift, GPU +2                                   │  │
│ │ AI recommendation: APPROVE (advisory only)                            │  │
│ │ [Open evidence] [Reject + reason] [Approve + reason]                   │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- inspect evidence；
- approve/reject；
- request more evidence/comment；
- open affected object。

## Dangerous actions

Approve/Reject 本身是 R3 Human-only。不得 batch approve 不同 scope 的高风险请求而不看 packet。

## Status / Evidence / Approval

Pending/Approved/Rejected/Expired/Withdrawn。Decision 写入 Evidence/Audit，不能修改历史决定，只能新建 superseding decision。

## AI distinction

AI recommendation 必须视觉上标 “Advisory”；按钮永远是 Human actor action。

## Edge states

- Empty：显示“无待审批”，并可看最近决定。
- Loading：queue skeleton，不预填 recommendation。
- Error：无法读取 packet 时禁用 Approve/Reject。
- Partial Failure：任何 required Evidence 缺失则 action disabled 并标 INCOMPLETE。
- Backend unavailable：受影响 backend down 作为 risk evidence，不阻断查看 Domain packet。
- Permission denied：非 Approver 只读或不可见，不能通过 deep link 获得按钮。

---

# 13. AI Operator

## Page Goal

让 AI 在用户真实 Authority 内跨域协作、执行 R0、准备 R1/R2 Decision Packet，并在越界前停下。

**Primary Role：** 所有允许使用 AI Operator 的角色；Authority 继承当前用户。

## Information hierarchy

1. Acting as / Scope / Environment / Policy；
2. conversation/task goal；
3. plan；
4. step-level R0/R1/R2/R3；
5. proposed action；
6. side effects；
7. Evidence destination；
8. Gate / Approval；
9. rollback/LKG；
10. execution timeline。

## Low-fi

~~~text
┌ AI Operator ────────────────────────────────────────────────────────────────┐
│ Acting as: principal_a | Project: proj_x | Env: Production | Policy: p17   │
│ Goal: promote candidate_x if safe, otherwise stop                           │
│                                                                              │
│ Plan                                                                         │
│ ✓ R0 Read candidate / production / LKG                                      │
│ ✓ R0 Collect Gate + Evidence                                                 │
│ → R1 Proposal: promote candidate_x                                          │
│ ! R2 Requires human approval                                                 │
│                                                                              │
│ Proposed action: traffic canary 10% → 50% → 100%                            │
│ Side effects: +2 GPU | Evidence: evidence_set_x | LKG: dep_old             │
│ Gate: PASS | Approval: PENDING                                               │
│ [Open Decision Packet] [Request Approval]                                   │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

## Main actions

- ask/analyze；
- generate plan；
- execute eligible R0 step；
- generate proposal；
- request approval；
- resume after approval；
- stop/cancel。

## Dangerous actions

AI Operator 自己没有危险动作白名单。任何 delete/promote/permission/policy/secret/backend admin 都按相同 contract。

## Status / Evidence / Approval

每步显示 Suggested / Proposed / Executed / Waiting Approval / Rejected / Failed / Rolled Back。Executed step 必须有 request/correlation/evidence refs。

## AI distinction

这是最严格页面：建议文字不能看起来像已执行；真正 execution 需要独立 event/timestamp/actor。

## Edge states

- Empty：新会话显示可做的 task examples，但不暗示额外权限。
- Loading：保留 plan/history，不重复提交 mutation。
- Error：tool/API 失败显示具体 step failed，可 bounded retry。
- Partial Failure：读到部分 Evidence 时明确 incomplete，不继续高风险 action。
- Backend unavailable：可诊断/规划，但不能伪造执行成功。
- Permission denied：AI 解释缺少权限并可生成 access request；禁止 self-escalate。

---

# 14. Cross-page Interaction Patterns

## 14.1 Candidate → Production

固定路径：

~~~text
Model/Capability
→ Candidate Deployment
→ Experiment/Evidence
→ Gate
→ Approval Inbox
→ Approved rollout
→ Production
→ Verify
→ LKG retained
~~~

任何页面都不能跳过中间 Gate/Approval。

## 14.2 Failure → LKG

~~~text
Home Attention
→ Deployment
→ Incident context
→ LKG proof
→ pre-authorized rollback OR Approval
→ Operation
→ post-check
→ Recovered to LKG
~~~

## 14.3 External Backend Detail

所有页面使用统一折叠区：

~~~text
Implementation details
Adapter
Backend type
ExternalRef
Observed health
Last sync
Diagnostics link if permitted
~~~

不在主标题使用 vendor 作为 Domain identity。

# 15. Contract-pending controls

P2-03 识别的 CG-01~CG-15 中，尚未完成 Northbound/State/Adapter Contract 的真实动作，在 Low-fi 中必须标：

**Contract Pending**

而不是假定 endpoint 已存在。

第一批受影响：

- Model/Dataset intake；
- Experiment reproduction create；
- Scheduler Policy mutation；
- checkpoint/preemption/resume；
- backend replacement；
- dependency risk exception；
- Agent Decision Packet read model；
- recover-to-LKG action。

这不阻塞任务流设计，但阻塞 P3 实装相应 control。

# 16. Accessibility / Safety Baseline for later Design System

Low-fi 已冻结以下非视觉要求，P2-06 不得反向破坏：

- 状态不只靠颜色；
- dangerous action 有文本风险说明；
- keyboard 可达；
- focus 顺序符合 task hierarchy；
- loading 不触发重复 mutation；
- error message 不泄露 secret；
- Approval packet 可在不看图表时理解；
- AI suggestion / execution 有文本标签；
- Production 环境有持续文本标识。

# 17. Acceptance Criteria

- [x] 12 个核心页面全部定义 Page Goal / Primary Role。
- [x] 每页有 information hierarchy / main actions / dangerous actions。
- [x] 每页定义 status / Evidence / Approval 位置或语义。
- [x] 每页区分 AI suggestion 与 execution。
- [x] 每页覆盖 Empty / Loading / Error / Partial Failure / Backend unavailable / Permission denied。
- [x] Candidate / Production / Failed / LKG 明确。
- [x] spec / status 明确。
- [x] External backend detail 明确不等于 Authority。
- [x] R0/R1/R2/R3 在可执行页面有可见表达。
- [x] Contract Pending controls 显式登记，不伪造能力。
- [x] 没有进入颜色、字体、视觉品牌或前端编码。

# 18. Exit Condition

WP-P2-05 完成。Low-fi 已足以启动 P2-06 Design System Direction，但 **P3 Repository Skeleton 仍不得被解释为可以实现全部业务动作**；P1-03/P1-04/P1-05 仍需先收敛 Journey 暴露的事件、状态机和 Adapter action contract。


# 19. Post-P1 Contract Closure Amendment

§15 的 Contract Pending 清单是 P2-05 冻结时的真实状态。

当前在 P1-03 / P1-04 / P1-05 / P1-CLOSE-01 后：

- Model/Dataset intake：已分配正式 API + Adapter Contract；
- Experiment/Reproduction create：已有 API；
- Scheduler Policy mutation：已有 GET/PATCH + State/Responsibility guard；
- checkpoint/resume：已有 API + TrainingRun State Machine + TrainingAdapter；
- backend replacement：已有 Adapter replacement Contract + API；
- dependency risk exception：使用 Approval Decision Packet + expiry；
- AI Operator Decision Packet：已有 ExecutionContext/Approval read model；
- recover-to-LKG：已有 Deployment recovery action + State Machine。

因此 Low-fi 核心 control 可以从 **Contract Pending** 转为 **Contracted / Not Implemented**。

这不表示功能已编码；P3/P8 实现仍必须通过 generated client 与 Contract CI。

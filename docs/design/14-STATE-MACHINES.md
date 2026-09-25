# State Machines v1.0

> Work Package：**WP-P1-04 State Machines**
>
> 状态：**Baseline Frozen v1.0**
>
> Machine-readable：contracts/state-machines/state-machines.v1.json
>
> 上位 Authority：Domain Model、Northbound API、Event Contract、Human-AI Responsibility、Golden Journeys。

# 1. 为什么需要 State Machine

Domain Object 的 status 不能由 UI、Agent 或第三方 Backend 任意 PATCH。

所有有业务意义的状态变化必须满足：

~~~text
Current State
+ Action
+ Actor / Principal
+ Scope / Environment
+ resource_version
+ Guard
+ Policy
+ Evidence
+ Gate
+ Approval
= Allowed Transition
~~~

然后：

~~~text
authoritative mutation
→ new resource_version
→ Evidence linkage
→ Domain Event
~~~

# 2. Common Transition Contract

每个 transition 至少定义：

- from；
- to；
- action；
- actor；
- responsibility；
- guard；
- required evidence；
- required approval；
- timeout；
- retry；
- compensation / rollback；
- emitted event。

## 2.1 禁止 status patch

禁止：

~~~text
PATCH status.phase = PRODUCTION
PATCH status.phase = READY
PATCH status.phase = APPROVED
~~~

必须使用显式 action，例如：

- promote；
- approve；
- resume；
- recover-to-lkg；
- accept-dependency。

status 只由 Controller 根据 transition 结果更新。

## 2.2 resource_version

所有 mutation transition 必须做 optimistic concurrency。

过期 resource_version：

- 不执行；
- 返回 412 RESOURCE_VERSION_MISMATCH；
- 调用方重新读取状态与 Evidence。

## 2.3 Long-running transition

以下默认返回 OperationReference：

- provisioning；
- training；
- evaluation；
- promotion rollout；
- rollback/recovery；
- migration；
- VM provision/deprovision。

Operation 完成不等于业务成功；Controller 验证 post-condition 后才写最终 state。

## 2.4 Failure 不等于删除历史

FAILED / REJECTED / RESTRICTED / BLOCKED 都是有效事实。

修复后：

- 可以产生新 revision；
- 可以创建新 Run / Approval；
- 可以从允许的 recoverable state 继续；

不能删除失败 Evidence 伪装成首次成功。

# 3. LKG 语义冻结

**LKG 是经过验证的 Deployment revision designation，不是主 lifecycle phase。**

原因：

- 当前 Production revision 可以同时是 LKG；
- rollback 的目标是某个 verified revision；
- “恢复至 LKG”完成后 Deployment 仍是 PRODUCTION，只是 active revision 指向 lkg_ref；
- 把 LKG 作为互斥 phase 会造成 PRODUCTION 与 LKG 无法同时表达。

因此 Deployment status 至少包含：

- phase；
- active_revision；
- lkg_ref；
- recovered_from_failure 可选；
- observed_at。

Event 使用 deployment.recovered_to_lkg。

# 4. ModelAsset State Machine

Baseline states：

~~~text
DISCOVERED
→ IMPORTING
→ CANDIDATE
→ VERIFIED
→ READY
→ DEPRECATED
→ RETIRED
~~~

Side states：

~~~text
QUARANTINED
RESTRICTED
FAILED
~~~

关键 transition：

| Action | From → To | Responsibility | Guard / Evidence | Recovery |
|---|---|---|---|---|
| begin-import | DISCOVERED → IMPORTING | R0 | source ref + provenance start | fail → FAILED/QUARANTINED |
| import-complete | IMPORTING → CANDIDATE | R0 | artifact digest + source/license evidence | new import revision |
| quarantine | any pre-READY → QUARANTINED | R0 policy | security/data/license risk | review action |
| verify | CANDIDATE → VERIFIED | R0 | capability probe + evaluation evidence | new evidence/revision |
| mark-ready | VERIFIED → READY | R0/R2 by policy | required Gate PASS | blocked until Gate |
| restrict | CANDIDATE/VERIFIED/READY → RESTRICTED | R0 policy / R2 manual | risk evidence | re-review |
| deprecate | READY → DEPRECATED | R1/R2 | impact analysis | replacement |
| retire | DEPRECATED → RETIRED | R2 if consumers | no active dependency | none |

FAILED 不直接回 READY；必须新 revision 或重新进入明确 import/verification flow。

# 5. DatasetAsset State Machine

Baseline：

~~~text
DISCOVERED / DECLARED
→ INGESTING
→ CURATING
→ CANDIDATE
→ READY
→ DEPRECATED
→ RETIRED
~~~

Side：

~~~text
QUARANTINED
RESTRICTED
FAILED
~~~

关键规则：

- ingest 不等于可训练；
- classification / provenance / license 未决时只能 quarantine/candidate；
- READY revision immutable；
- 数据内容、split、label policy 改变产生新 business revision；
- classification downgrade 属 R2；
- sensitive external transfer 单独 Approval，不通过 state shortcut。

Retry：

- parser/transient source failure 可 bounded retry；
- final FAILED 后重试生成新 intake attempt/Evidence；
- 不覆盖原 content hash。

# 6. Deployment State Machine

主 phase：

~~~text
DRAFT
→ CANDIDATE
→ PROVISIONING
→ STAGING
→ READY
→ PROMOTING
→ PRODUCTION
→ DRAINING
→ RETIRED
~~~

运行异常：

~~~text
DEGRADED
FAILED
ROLLING_BACK
~~~

LKG 是 orthogonal designation。

## 6.1 Promotion

~~~text
READY
  │
  ├─ Gate FAIL → stay READY + GATE_BLOCKED
  │
  ├─ Approval required/pending → stay READY
  │
  └─ Gate PASS + valid Approval/policy
          ↓
      PROMOTING
          ↓ rollout post-check PASS
      PRODUCTION
~~~

Promotion request 本身不提前把 phase 改成 PROMOTING。

## 6.2 Failure / Rollback

~~~text
PRODUCTION
→ DEGRADED
→ bounded recovery
   ├─ PASS → PRODUCTION
   └─ FAIL → ROLLING_BACK
                 ↓
          verified lkg_ref
                 ↓
            PRODUCTION
        (active_revision = LKG)
~~~

失败 candidate 保留 Evidence。

## 6.3 Promotion Guard

必须同时满足：

- expected resource_version；
- candidate revision immutable/pinned；
- target environment；
- GateResult PASS；
- required Approval APPROVED；
- valid LKG ref；
- rollout strategy；
- rollback path；
- no blocking dependency/security policy。

# 7. TrainingRun State Machine

~~~text
QUEUED
→ ADMITTED
→ PREPARING
→ RUNNING
→ CHECKPOINTING
→ RUNNING
→ SUCCEEDED
~~~

Side：

~~~text
PAUSED
PREEMPTED
FAILED
CANCELED
~~~

## 7.1 Preemption

安全抢占：

~~~text
RUNNING
→ CHECKPOINTING
→ checkpoint VERIFIED
→ PREEMPTED
→ resource released
~~~

恢复：

~~~text
PREEMPTED / PAUSED
→ ADMITTED
→ PREPARING
→ checkpoint restore verified
→ RUNNING
~~~

禁止：

- checkpoint 未验证就把最后可恢复资源当已安全释放；
- PREEMPTED 直接改 SUCCEEDED；
- final FAILED 重置为 RUNNING 掩盖历史。

## 7.2 Retry

Run 内 transient retry 必须记录 attempt。

超过 retry budget：

- transition FAILED；
- emit run.retry.exhausted；
- 新一轮完整 retry 应创建新 Run 或显式 lineage，不能 rewrite 原 run。

# 8. EvaluationRun State Machine

~~~text
QUEUED
→ ADMITTED
→ PREPARING
→ RUNNING
→ SUCCEEDED
~~~

Terminal / side：

~~~text
FAILED
CANCELED
INVALIDATED
~~~

INVALIDATED 用于：

- evaluator contract 错误；
- dataset/rubric contamination；
- evidence integrity 失败。

质量差不是 INVALIDATED；质量差仍可 SUCCEEDED + Gate FAIL。

Retry final FAILED 默认创建新 EvaluationRun，并使用 lineage 表达 retry/replaces。

# 9. Experiment State Machine

~~~text
DRAFT
→ PLANNED
→ READY
→ RUNNING
→ COMPLETED
→ ARCHIVED
~~~

Side：

~~~text
BLOCKED
FAILED
CANCELED
~~~

规则：

- PLANNED → READY 要求 pinned source/revision/environment/acceptance；
- READY → RUNNING 创建/关联 Run；
- RUNNING → COMPLETED 表示 experiment contract 已产生可解释结论，不要求 candidate 一定优于 baseline；
- result 不理想仍可 COMPLETED；
- FAILED 表示 experiment execution/contract 无法完成；
- 改 hypothesis / acceptance criteria 形成新 experiment revision，不能原地改后声称同一实验。

# 10. Approval State Machine

~~~text
REQUESTED
→ PENDING
→ APPROVED / REJECTED
~~~

其他终态/分支：

~~~text
CHANGES_REQUESTED
CANCELED
EXPIRED
REVOKED
~~~

## 10.1 Human-only decision

PENDING → APPROVED / REJECTED 的最终 decision actor 必须是授权 Human Principal。

Agent：

- 可以创建 request；
- 可以生成 Decision Packet；
- 可以提醒；
- **不能成为 final_decider**；
- **不能 self-approve**。

## 10.2 Packet completeness

REQUESTED → PENDING 之前至少具备：

- requested action；
- requester；
- scope/environment；
- responsibility level；
- affected objects；
- required Evidence；
- Gate state；
- side effects；
- rollback/LKG where applicable；
- expiry。

Evidence 不完整时保持 REQUESTED/CHANGES_REQUESTED，不允许 Approve 按钮伪装可用。

## 10.3 Re-request

REJECTED / EXPIRED / CHANGES_REQUESTED 后需要新的 Approval record 或 revision linkage，不覆盖旧 decision。

REVOKED 只撤销未消费的批准或触发后续治理动作；已执行真实副作用不会因 revoke 自动“时间倒流”。

# 11. VM State Machine

~~~text
PLANNED
→ PROVISIONING
→ STOPPED / RUNNING
→ DRAINING
→ STOPPED
→ DEPROVISIONING
→ RETIRED
~~~

异常：

~~~text
FAILED
UNKNOWN
~~~

规则：

- backend VM ID 只在 ExternalRef；
- PROVISIONING/DEPROVISIONING 是 async Operation；
- Production VM drain/reboot/deprovision 受 Policy/Approval；
- UNKNOWN 不是 FAILED，表示 observation 丢失；
- UNKNOWN 时不允许未经 guard 直接 deprovision；
- destroy/deprovision 前必须证明无 authoritative data 或已有迁移/backup Evidence。

# 12. UpstreamDependency Risk State Machine

~~~text
DISCOVERED
→ UNDER_REVIEW
→ ACCEPTED / RESTRICTED / REJECTED
→ ACTIVE
→ AT_RISK
→ MIGRATING
→ REPLACED
→ RETIRED
~~~

## 12.1 Risk trigger

ACTIVE → AT_RISK 可以由：

- license change；
- critical CVE/security；
- EOL；
- upstream health；
- supply-chain integrity；
- incompatible revision；
- data portability risk。

风险事件可以自动触发 Policy block，但不能自动把风险标回 ACCEPTED。

## 12.2 Migration

AT_RISK → MIGRATING 需要：

- replacement candidate；
- migration plan；
- data/config portability proof target；
- rollback；
- affected object graph。

MIGRATING → REPLACED 需要 conformance + cutover Evidence。

## 12.3 License/Security Override

Override 是 **Approval/Policy exception with scope + TTL**，不是 dependency state。

因此：

- AT_RISK 仍保持 AT_RISK；
- override 只允许受限行为；
- 到期重新阻断；
- AI 不做最终 override decision。

# 13. GateResult Semantics

GateResult 建议作为 immutable evaluation result，而不是可任意编辑 state machine。

一个 GateResult 至少固定：

- subject/revision；
- gate definition revision；
- checks；
- PASS / FAIL / BLOCKED；
- Evidence refs；
- evaluated_at。

新 Evidence 触发新的 GateResult，不原地把 FAIL 改 PASS。

# 14. Cross-machine Invariants

## 14.1 Production Promotion

~~~text
Model/Dataset/Experiment/Run Evidence
→ GateResult PASS
→ Approval APPROVED if required
→ Deployment READY → PROMOTING
→ rollout
→ Deployment PRODUCTION
~~~

## 14.2 Agent + Approval

~~~text
Agent action proposed
→ Approval REQUESTED/PENDING
→ Human decision
→ APPROVED
→ same Workflow resumes
→ Northbound action
→ audit.action.executed
~~~

Agent 不得通过新 Workflow 绕过旧 REJECTED decision 而保持同一 action intent；重新请求必须有新 Evidence/理由。

## 14.3 Failure → LKG

~~~text
Deployment PRODUCTION
→ DEGRADED
→ bounded recovery FAIL
→ ROLLING_BACK
→ lkg_ref verified
→ active_revision = LKG revision
→ PRODUCTION
→ deployment.recovered_to_lkg Event
~~~

# 15. Timeout / Retry Baseline

状态机只冻结语义，不把所有秒数硬编码。

必须存在：

- operation timeout；
- retry budget；
- backoff；
- max attempts；
- approval expiry；
- stale observation threshold；
- recovery escalation threshold。

具体值属于 Policy/spec，不属于 backend default。

# 16. Compensation vs Rollback

Compensation 不是数据库 history rewrite。

例：

- Promotion 部分成功 → traffic rollback to LKG；
- Dataset ingest 失败 → quarantine temporary artifact；
- VM provision 失败 → cleanup allocated resource；
- backend cutover 失败 → restore previous Adapter route。

每次 compensation 都产生新 Evidence/Event。

# 17. Event Alignment

P1-04 使用 P1-03 Event Contract，并补充以下 additive event types：

- model.status.changed
- dataset.status.changed
- experiment.status.changed
- deployment.status.changed
- vm.status.changed
- dependency.status.changed
- approval.status.changed
- gate.evaluated

它们只是状态变化事实，不取代更具体的 rollout/approval/risk 事件。

# 18. Contract Gap Closure

本 WP 收敛：

- **CG-03** checkpoint/resume action semantics：state guard 已冻结；具体 TrainingAdapter method 待 P1-05。
- **CG-07** Scheduler Policy mutation：责任/guard 原则已冻结；Northbound endpoint 仍待 API extension。
- **CG-08** checkpoint/preemption/resume orchestration：**STATE SEMANTICS CLOSED**。
- **CG-11** Dependency risk lifecycle：**STATE SEMANTICS CLOSED**；read API 待 extension。
- **CG-12** time-bounded governance exception：**SEMANTICS CLOSED**，使用 Approval/Policy exception，不改 dependency risk。
- **CG-13** Agent/Decision Packet：Approval packet + Human-only decision 已冻结；read model endpoint 待 extension。
- **CG-14** recover-to-LKG：**STATE SEMANTICS CLOSED**；Northbound action endpoint 待 extension。

# 19. Acceptance Criteria

- [x] Model Lifecycle 冻结。
- [x] Dataset Lifecycle 冻结。
- [x] Deployment Lifecycle / Promotion / LKG / rollback 冻结。
- [x] TrainingRun / EvaluationRun Lifecycle 冻结。
- [x] Experiment Lifecycle 冻结。
- [x] Approval Lifecycle 与 Human-only final decision 冻结。
- [x] VM Lifecycle 冻结。
- [x] Dependency Risk Lifecycle / TTL override 冻结。
- [x] transition 统一包含 guard/evidence/approval/retry/rollback 语义。
- [x] resource_version optimistic concurrency 适用于 mutation transition。
- [x] status 不能被客户端直接 PATCH。
- [x] Machine-readable baseline 已提供。
- [x] Event Contract 已做 additive 对齐。

# 20. Exit Condition

WP-P1-04 完成。下一步进入 WP-P1-05 Adapter Contract；Adapter method 必须遵守这里的 state transition guard，不得自己定义第二套 lifecycle。

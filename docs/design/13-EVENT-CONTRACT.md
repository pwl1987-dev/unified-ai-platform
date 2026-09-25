# Event Contract v1.0

> Work Package：**WP-P1-03 Event Contract**
>
> 状态：**Baseline Frozen v1.0**
>
> Machine-readable：
> - contracts/events/event-envelope.schema.json
> - contracts/events/event-catalog.v1.json
>
> 上位 Authority：Functional Architecture、Technology Stack、Domain Model、Northbound API、P1 Decision Register。

# 1. 目的

Event Contract 解决：

> Control Hub 中已经发生的权威事实，如何可靠、可重放、可关联地通知 Scheduler、Workflow、Agent、UI read model、Audit 与外部 Adapter，而不制造第二 Authority。

冻结链路：

~~~text
authoritative mutation
→ PostgreSQL transaction / outbox intent
→ immutable Domain Event
→ NATS JetStream transport
→ idempotent consumers
→ read model / workflow reaction / evidence linkage
~~~

NATS/JetStream 是 transport implementation，不拥有 Event semantics。

# 2. Event 不是 Command

Event 只描述已经发生的事实：

- deployment.rollout.started
- approval.decided
- run.status.changed

禁止把以下“希望发生”的指令伪装成 Event：

- please.promote
- force.delete
- restart.gpu

命令/Action 必须先经过 Northbound API、Policy、Gate、Approval，再由 Control Hub 改变权威状态；状态成功写入后才发布 Event。

# 3. Common Event Envelope

所有事件必须包含：

- event_id
- event_type
- schema_version
- payload_version
- producer
- occurred_at
- subject
- project_ref
- actor
- correlation_id
- idempotency_key
- payload

按需包含：

- causation_id
- trace_id
- resource_version
- business_revision
- evidence_refs
- external_refs
- policy_refs
- operation_ref
- workflow_ref

## 3.1 event_id

平台生成、全局唯一、不可变。

规范形式：

~~~text
event_<uuidv7>
~~~

event_id 只做事件 identity，不替代 subject Domain ID。

## 3.2 event_type

稳定 semantic name，不携带 vendor 名：

~~~text
deployment.rollout.completed
approval.decided
dependency.risk.changed
~~~

禁止：

~~~text
vllm.server.started
harbor.tag.changed
mlflow.run.finished
~~~

vendor/backend observation 必须先通过 Adapter 正规化为平台事件或 ExternalRef。

## 3.3 schema_version vs payload_version

- schema_version：Envelope schema 版本；
- payload_version：该 event_type payload 合约版本。

两者独立。

## 3.4 producer

producer 是平台逻辑组件：

- control-hub
- scheduler
- workflow-controller
- resource-controller
- agent-controller
- adapter-controller
- governance-controller

不能使用随机容器名作为 contract producer identity。

## 3.5 subject

统一：

~~~text
kind
id
~~~

kind 必须是平台 Domain Object 或明确 read-model subject。

## 3.6 project_ref / actor

- project_ref：Stage-1 Scope Authority；
- actor：PrincipalRef；系统自动动作使用 service-account Principal；
- Agent 触发动作仍必须记录 effective Principal，并可在 payload 中附 agent_ref。

## 3.7 correlation / causation / trace

- correlation_id：同一业务旅程/请求链；
- causation_id：直接导致本事件的上一个 event_id 或 action/operation reference；
- trace_id：OpenTelemetry trace 关联。

三者不能混用。

## 3.8 idempotency_key

事件 producer 为同一 logical transition 生成稳定 idempotency_key。

Consumer 必须按 event_id 或 producer + idempotency_key 去重。

# 4. Delivery Semantics

Baseline：

- **at-least-once delivery**
- consumer **must be idempotent**
- 不承诺全局 total order
- 对同一 subject 提供可检测顺序

顺序依据：

1. resource_version；
2. subject_sequence（未来可选）；
3. occurred_at 仅用于时间展示，不作为强一致排序唯一依据。

Consumer 收到旧 resource_version 事件，不得覆盖新 read model。

# 5. Transaction / Outbox Rule

authoritative mutation 与 Event intent 必须保持原子一致性。

Stage-1 推荐：

~~~text
PostgreSQL authoritative transaction
+ transactional outbox
→ publisher
→ JetStream
~~~

禁止：

~~~text
DB commit 成功
→ 进程崩溃
→ event 永久丢失
~~~

也禁止先发 Event 再尝试写 Authority。

# 6. Replay

Event 可以重放，但 replay 不能重新执行不可逆副作用。

Consumer 必须区分：

- rebuild read model；
- rebuild search/index；
- reconstruct audit view；
- trigger live mutation。

只有前 3 类可由 event replay 默认触发。

live side-effect consumer 必须有 fencing / operation state guard，避免 replay 导致重复 Promotion、Delete、Publish。

# 7. Evidence

重要状态变化 Event 应带 evidence_refs，但 Event 本身不是 Evidence 内容存储。

至少以下必须有关联 Evidence：

- Gate blocked/pass；
- Approval decision；
- Promotion/rollback；
- Recovery to LKG；
- training/evaluation completion；
- dependency/license/security risk；
- destructive or privileged action。

failed Evidence 不因 Event replay 删除。

# 8. Secret / Sensitive Data

Event payload 禁止：

- secret plaintext；
- API key/token；
- private credential；
- raw sensitive dataset content；
- full prompt containing secret。

只允许 secret_ref / credential_ref 等 opaque reference。

Security Event 允许记录分类后的 risk metadata，不记录 exploit secret。

# 9. Compatibility

同一 event_type 的兼容规则：

允许 additive：

- 新增 optional field；
- 新增 metadata；
- 新增 enum 时 consumer 必须 unknown-safe。

不允许静默 breaking：

- 删除 required field；
- 改字段语义；
- 改 subject identity；
- 把 stable ID 换成 ExternalRef。

Breaking payload 必须提升 payload_version，并提供迁移窗口。

# 10. Baseline Event Families

## 10.0 P1-04 additive state-transition events

为避免 State Machine 为每个 transition 发明私有事件，P1-04 以 backward-compatible additive 方式补充：

- model.status.changed
- dataset.status.changed
- experiment.status.changed
- deployment.status.changed
- vm.status.changed
- dependency.status.changed
- approval.status.changed
- gate.evaluated

这些事件只表达状态变化事实；更具体的 rollout / approval.decided / dependency.risk.changed 等事件仍优先使用。

## 10.1 Resource Events

- resource.observation.updated
- resource.health.changed

用途：GPU/Node/VM/Environment observation、capacity read model。

注意：高频 telemetry 不应把每个采样点都变成 Domain Event；原始 metrics 进入 Observability backend，只有有业务意义的 snapshot/change 形成 Event。

## 10.2 Run / Job Events

- run.created
- run.status.changed
- run.checkpoint.created
- run.retry.exhausted

适用 TrainingRun / EvaluationRun / long-running operation。

## 10.3 Deployment Events

- deployment.candidate.created
- deployment.promotion.requested
- deployment.promotion.blocked
- deployment.rollout.started
- deployment.rollout.completed
- deployment.rollback.started
- deployment.recovered_to_lkg

Promotion requested 只表示平台已经创建受控 promotion intent/operation，不表示已经批准或上线。

## 10.4 Model Events

- model.revision.created
- model.validation.completed

business revision 与 resource_version 继续分离。

## 10.5 Dataset Events

- dataset.revision.created
- dataset.classification.changed

classification downgrade 的 event 必须能关联 Approval/Evidence。

## 10.6 Security / Dependency Events

- security.risk.detected
- dependency.risk.changed

Critical risk 可以驱动 Attention/Gate，但不能由 Event consumer 自行 lower Gate。

## 10.7 Approval Events

- approval.requested
- approval.decided
- approval.expired

approval.decided 必须记录 Human Principal；AI Agent 不能成为 final_decider。

## 10.8 Audit Events

- audit.action.executed

记录：

- effective actor；
- action；
- object；
- scope；
- environment；
- responsibility level；
- request/correlation；
- result；
- evidence refs。

Audit Event 不是替代 Domain object history，而是统一审计投影输入。

## 10.9 Agent Events

- agent.plan.created
- agent.action.proposed
- agent.action.executed

必须体现 suggestion ≠ execution。

agent.action.executed 必须引用实际 Northbound request/operation，不允许 Agent 自报“已执行”。

## 10.10 Incident / Recovery Events

- incident.opened
- incident.recovery.completed

recovery.completed 必须引用 LKG、post-check Evidence 与恢复后的 Deployment/Capability status。

# 11. Payload Minimums

## run.status.changed

至少：

- run_ref
- from_phase
- to_phase
- reason_code
- observed_at

可选：

- progress
- checkpoint_ref
- external_job_ref

## deployment.rollout.started

至少：

- deployment_ref
- candidate_revision
- target_environment
- rollout_strategy
- gate_result_ref
- approval_ref
- lkg_ref

## approval.decided

至少：

- approval_ref
- decision
- decided_by
- decided_at
- reason
- affected_action_ref

## dependency.risk.changed

至少：

- dependency_ref
- from_risk
- to_risk
- reason
- affected_object_refs
- evidence_refs

## agent.action.executed

至少：

- agent_ref
- effective_principal_ref
- action
- responsibility_level
- request_ref
- result
- evidence_refs

## incident.recovery.completed

至少：

- incident_ref
- affected_deployment_ref
- recovered_lkg_ref
- operation_ref
- post_check
- evidence_refs

# 12. UI / Attention Consumption

Event → Attention 不是一一映射。

例如：

- run.status.changed = SUCCEEDED → Notification；
- run.retry.exhausted → Needs Your Attention；
- approval.requested → Needs Your Attention for Approver；
- deployment.rollout.completed → Notification；
- dependency.risk.changed = CRITICAL → Needs Your Attention + Gate impact。

Attention rule 属于 Governance/Policy，不写死在 producer。

# 13. Agent Consumption

Agent 可以订阅/读取 Event projection 做：

- detect change；
- propose next step；
- correlate incident；
- resume Workflow。

但 Agent 不能仅因收到 Event 就执行超出当前 Principal/Policy 的 mutation。

每次副作用仍回 Northbound API。

# 14. Adapter Boundary

Adapter 可以产生 raw observation，但必须由 Adapter Controller 正规化后形成 Event。

例如：

~~~text
vLLM health JSON
→ ServingAdapter observation
→ Control Hub/Controller decides status transition
→ deployment/status Event
~~~

而不是把 vLLM JSON 直接广播成平台 Event Contract。

# 15. Contract Gap Closure from P2-03

本 WP 部分收敛：

- CG-05：UpstreamDependency risk change 有事件语义；read API 仍待 P1-02 extension。
- CG-13：Agent execution context 已进入 agent.action.* Event minimum；Decision Packet read model 仍待 P1-04。
- CG-15：incident/recovery 事件已冻结；read model/action 仍待 P1-04/P1-02 extension。

没有把未完成部分伪装为已关闭。

# 16. Machine-readable Catalog

contracts/events/event-catalog.v1.json 记录：

- event_type
- family
- subject_kinds
- payload_version
- required_payload_fields
- attention_candidate
- evidence_required

Catalog 是 contract index，不是 runtime registry Authority。

# 17. Acceptance Criteria

- [x] 覆盖 Resource / Job / Deployment / Model / Dataset / Security / Approval / Audit。
- [x] 增补 Dependency / Agent / Incident 以覆盖 Golden Journeys。
- [x] Envelope 包含 schema version / event id / producer / timestamp / correlation id / idempotency key / payload version。
- [x] Event 与 Command 分离。
- [x] at-least-once + idempotent consumer。
- [x] 同 subject ordering 可由 resource_version 检测。
- [x] transaction/outbox 边界明确。
- [x] replay 不可重复真实副作用。
- [x] secret plaintext 禁止进入 Event。
- [x] Agent action Event 记录 effective Principal。
- [x] Approval decision 只能由 Human Principal 完成。
- [x] Backend raw DTO 不成为 Event Contract。
- [x] 提供 JSON Schema + machine-readable catalog。

# 18. Exit Condition

WP-P1-03 完成。下一步进入 WP-P1-04 State Machines；State Machine 必须引用这里的 event_type，而不是重新发明第二套事件命名。

# Adapter Contract v1.0

> Work Package：**WP-P1-05 Adapter Contract**
>
> 状态：**Baseline Frozen v1.0**
>
> Machine-readable：
> - contracts/adapters/adapter-manifest.schema.json
> - contracts/adapters/adapter-catalog.v1.json
>
> 上位 Authority：
> - Functional Architecture
> - Technology Stack
> - Core Domain Model
> - Northbound API Boundary
> - P1 Decision Register
> - Event Contract
> - State Machines
>
> 核心原则：**Adapter 是可替换实现边界，不是 Domain Authority。**

# 1. 为什么需要 Adapter Contract

平台必须允许替换：

- 模型来源；
- 资产 Hub；
- Provider；
- Serving Runtime；
- Training / Experiment Backend；
- Vector / Search；
- Workflow；
- Messaging；
- Virtualization；
- Secret；
- Object Storage；
- Identity；
- OCI Registry。

替换这些 Backend 时，不能要求：

- UI 改用 vendor DTO；
- Application 改写 /v1 payload；
- Domain stable ID 变化；
- Gate / Approval / lifecycle 改成 vendor 状态机；
- Agent 获得 backend admin side channel。

冻结关系：

~~~text
Northbound API / Domain / State Machine / Policy
                    ↓
             Adapter Contract
                    ↓
          replaceable Backend
~~~

# 2. Adapter Authority Boundary

Adapter **可以**：

- capability probe；
- validate config；
- 调用 Backend；
- 观察 Backend；
- 标准化 Backend error；
- 生成 ExternalRef；
- 返回 Evidence material；
- 实现 State Machine 已允许的 primitive。

Adapter **不能**：

- 创建或更改平台 stable Domain ID；
- 决定最终 lifecycle；
- 把 backend status 直接写成 authoritative status；
- 自行判定 Gate PASS；
- 自行做 Human Approval；
- 降低 Policy；
- 删除失败 Evidence；
- 把 secret plaintext 暴露给 UI / Agent；
- 直接向 Northbound caller 暴露 vendor DTO；
- 在 Control Hub 之外维持第二份业务 Authority。

Controller 负责：

~~~text
Adapter observation
→ validate / normalize
→ apply Domain guard
→ authoritative mutation
→ Evidence
→ Event
~~~

# 3. 第一批 Adapter Kind

P1-D01 / D02 后，第一批正式冻结为：

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

其中：

- AssetSourceAdapter 与 AssetHubAdapter 分离；
- ProviderAdapter 与 ServingAdapter 分离；
- OCIRegistryAdapter 与 ObjectStorageAdapter 分离。

# 4. Adapter Domain Object vs Adapter Implementation

平台已有一等 Domain Object：**Adapter**。

Adapter Domain Object 保存：

- stable adapter_id；
- kind；
- implementation reference；
- contract_version；
- implementation_version；
- config_ref；
- secret_refs；
- capability set；
- conformance status；
- health observation；
- external refs；
- Evidence refs；
- lifecycle。

真正的 binary/container/library/plugin 是可替换 implementation Artifact。

因此：

~~~text
Adapter Domain Object
  └── implementation Artifact / package / endpoint
          └── vendor backend
~~~

implementation 升级不必改变 adapter_id；发生不兼容语义变化时必须新 business revision / conformance Evidence。

# 5. Adapter Manifest

每个 implementation 必须声明 machine-readable manifest：

- adapter_kind；
- adapter_contract_version；
- implementation_name；
- implementation_version；
- implementation_revision/digest；
- supported_operations；
- capabilities；
- config_schema_ref；
- secret_usage；
- timeout/cancellation 支持；
- idempotency 支持；
- streaming 支持（适用时）；
- health probe；
- conformance profile；
- license / source / SBOM refs；
- minimum platform contract version；
- optional feature flags。

Manifest 是声明，不代表 READY。

真实 READY 需要：

~~~text
Manifest
+ Config validation
+ Capability probe
+ Conformance test
+ Security/License Evidence
= Adapter READY
~~~

# 6. Common Invocation Context

所有 Adapter action 必须收到统一 ExecutionContext，不允许各 Backend 自造权限上下文：

~~~text
ExecutionContext {
  request_id
  correlation_id
  operation_id?
  workflow_ref?
  project_ref
  effective_principal_ref
  agent_ref?
  environment
  responsibility_level
  idempotency_key?
  deadline
  resource_ref?
  expected_resource_version?
  policy_refs[]
  secret_refs[]
  trace_context?
}
~~~

规则：

1. Agent 调用必须保留 effective Principal；
2. Adapter 不重新解释 RBAC；
3. secret_refs 只可在允许的执行边界解析；
4. deadline 到期必须停止或进入可审计 cancellation path；
5. expected_resource_version 由 Controller guard，Adapter 不以 vendor revision 替代。

# 7. Common Result Contract

所有 Adapter operation 返回统一结果壳：

~~~text
AdapterResult {
  outcome
  retryable
  normalized_error?
  external_refs[]
  observations{}
  evidence_material_refs[]
  usage?
  backend_revision?
}
~~~

outcome：

- SUCCEEDED
- ACCEPTED
- FAILED
- UNKNOWN

**UNKNOWN** 用于：

- 请求可能已送达，但结果不可确认；
- backend observation 丢失；
- timeout 后无法安全判断副作用是否发生。

UNKNOWN 不允许由调用方直接当 FAILED 重试；必须先 reconcile。

# 8. Error Normalization

Adapter 必须把 vendor error 映射为稳定 taxonomy：

- INVALID_CONFIG
- UNSUPPORTED_CAPABILITY
- BACKEND_AUTH_FAILED
- BACKEND_POLICY_DENIED
- BACKEND_NOT_FOUND
- BACKEND_CONFLICT
- BACKEND_RATE_LIMITED
- BACKEND_UNAVAILABLE
- BACKEND_TIMEOUT
- TRANSIENT_FAILURE
- PERMANENT_FAILURE
- DATA_INTEGRITY_FAILURE
- CANCELED
- UNKNOWN_OUTCOME

Northbound API 再把这些映射到平台 ErrorEnvelope。

Vendor error code/message 可以作为 diagnostics/Evidence material 保存，但不能成为 API contract。

# 9. Retry / Idempotency / Reconciliation

## 9.1 Read operation

默认可 retry，受 deadline/backoff 限制。

## 9.2 Mutation operation

必须声明：

- idempotent；
- idempotent_with_key；
- non_idempotent；
- reconcile_required。

对可能产生真实副作用的 mutation：

1. 优先传 Idempotency-Key；
2. timeout 后不盲目重发；
3. 先 reconcile external state；
4. Controller 决定下一步 transition。

## 9.3 Adapter 禁止隐藏 retry

Adapter 可以做 transport-level bounded retry，但：

- 不能跨越 state transition；
- 不能把多次 destructive mutation 隐藏在一次调用里；
- retry 次数/延迟应可观测；
- final result 必须反映是否可能 UNKNOWN。

# 10. Timeout / Cancellation

所有 long-running Backend action 必须支持至少一种：

- native cancellation；
- cooperative cancellation；
- cancel-not-supported + reconciliation。

平台 Operation cancellation 不等于“杀进程即成功”。

Adapter 必须返回 cancellation capability，Controller 根据 State Machine 选择：

- cancel；
- checkpoint then cancel；
- drain；
- leave running and mark intervention required。

# 11. Capability Negotiation

平台不得通过：

~~~text
if vendor == "vllm"
if version >= x.y
~~~

在 Domain 层决定能力。

Adapter 必须通过 capability negotiation 声明：

- operation support；
- modality；
- streaming；
- checkpoint；
- rollout primitive；
- GPU/runtime feature；
- index/search feature；
- auth mode；
- consistency；
- max limits。

版本号可以作为 Evidence，但 capability probe 才决定是否可用。

# 12. Conformance Levels

统一四级：

- **C0 — Manifest Valid**：Schema 合法。
- **C1 — Contract Conformant**：required operations、errors、idempotency、timeout、ExternalRef 通过。
- **C2 — Journey Conformant**：至少一个对应 Golden Journey 的真实路径通过。
- **C3 — Production Eligible**：security/license/observability/recovery/replaceability Gate 通过。

Production Backend 至少 C3。

开发 candidate 可以 C1/C2，但 UI 必须显示非 Production Eligible。

# 13. ProviderAdapter

用途：外部/异构 AI API 能力。

Baseline operations：

- probe_capabilities
- health
- invoke
- invoke_stream
- usage_observe
- reconcile_request

ProviderAdapter 不管理我方 Deployment lifecycle。

请求/响应必须映射到 Capability semantics。

禁止：

- Provider model name 成为 Northbound stable model；
- Provider API key 进入普通 payload；
- raw Provider error 直接透传；
- Provider router 自行覆盖 Control Hub Policy。

# 14. ServingAdapter

用途：我方可控 Runtime/Deployment implementation，例如 SGLang、vLLM、llama.cpp、BentoML 形态。

Baseline operations：

- validate_deployment
- provision
- observe
- start
- stop
- drain
- endpoint_observe
- rollout_step
- rollback_step
- collect_evidence_material
- reconcile

ServingAdapter 只提供 primitive。

它不能：

- 自行把 Deployment 改成 PRODUCTION；
- 自行挑选 LKG；
- 绕过 Gate/Approval；
- 把 runtime CLI 参数提升为 Northbound contract。

ProviderAdapter 与 ServingAdapter 共享最小 Capability Conformance：

- modalities；
- input/output normalization；
- streaming；
- usage；
- error taxonomy；
- health/readiness；
- trace correlation。

# 15. AssetSourceAdapter

用途：发现、解析、获取外部 Model/Dataset/Artifact 来源。

Baseline：

- discover
- resolve
- metadata
- license
- provenance
- fetch
- verify_digest
- health

AssetSourceAdapter 不负责内部 catalog governance / publish。

外部 model/dataset ID 只作为 ExternalRef。

# 16. AssetHubAdapter

用途：内部/受控资产 Hub：

- catalog
- mirror
- publish
- replication
- retention
- resolve_mirror
- health

它不拥有 ModelAsset / DatasetAsset lifecycle。

同一产品可以同时实现 AssetSourceAdapter + AssetHubAdapter，但 conformance 独立。

# 17. ExperimentAdapter

用途：复用 tracking/experiment backend。

Baseline：

- create_projection
- log_metric
- log_artifact_ref
- log_parameter
- query_projection
- export_projection
- health

Experiment Domain Object、TrainingRun/EvaluationRun status、GateResult 仍由 Control Hub Authority 决定。

例如 MLflow Run ID 只能是 ExternalRef。

# 18. TrainingAdapter

Baseline：

- validate_run
- render_job
- start
- observe
- checkpoint
- pause
- resume
- cancel
- collect_outputs
- reconcile

必须遵守 P1-04 TrainingRun 状态机：

- checkpoint VERIFIED 后才允许安全 preempt；
- resume 不能抹掉 attempt history；
- Backend job SUCCESS 只是一条 observation，不自动等于 TrainingRun SUCCEEDED；
- outputs/digest/Evidence 完整后由 Controller transition。

这关闭 CG-03 的 Adapter method 部分。

# 19. VectorAdapter

Baseline：

- probe_capabilities
- create_index_projection
- upsert
- delete_projection
- query
- rebuild
- snapshot_metadata
- health

Index 是 derivative。

Vector collection ID 是 ExternalRef；Index 丢失必须可从 Knowledge/Dataset + recipe 重建。

# 20. SearchAdapter

Baseline：

- probe_capabilities
- index_projection
- remove_projection
- query
- rebuild
- health

Search backend 不拥有 canonical document/knowledge。

VectorAdapter 与 SearchAdapter 可以由同一产品实现，但 Contract 不合并。

# 21. WorkflowAdapter

用途：把我方 Workflow plan 映射到外部执行 Backend。

Baseline：

- submit_execution
- observe
- signal
- cancel
- resume
- reconcile

WorkflowAdapter 不拥有：

- Workflow plan Authority；
- Approval；
- Policy；
- Agent permission；
- retry budget decision。

Backend Workflow ID 只为 ExternalRef。

# 22. MessagingAdapter

Baseline：

- publish
- subscribe
- acknowledge
- consumer_health
- stream_health

要求：

- 传输 P1-03 Event Envelope；
- 不修改 event_type/payload semantics；
- at-least-once；
- consumer dedupe；
- no secret plaintext。

NATS + JetStream 是当前实现，不是 Contract。

# 23. VirtualizationAdapter

Baseline：

- probe_capabilities
- validate_vm_spec
- provision
- observe
- start
- stop
- drain
- snapshot_ref
- deprovision
- reconcile

遵守 VM 状态机。

libvirt UUID / VMware MoRef / Proxmox VMID 都只能为 ExternalRef。

Production deprovision 需要 Controller 已完成 data-safety/Approval guard。

# 24. SecretAdapter

SecretAdapter 是唯一允许解析 secret value 的 Adapter boundary 之一。

Baseline：

- create_or_import_ref
- lease_for_execution
- rotate
- revoke
- metadata
- health

关键规则：

- **没有“return plaintext secret to UI/Agent” operation**；
- lease_for_execution 只返回给受控 execution target；
- secret value 不进入 Domain DB；
- 不进入 Event；
- 不进入 Evidence；
- 不进入日志/prompt；
- AdapterResult 中不得携带 plaintext。

# 25. ObjectStorageAdapter

Baseline：

- put
- get_stream
- head
- list_prefix
- delete_object
- verify_digest
- health

平台 Artifact Authority 保存：

- Artifact stable ID；
- digest；
- size；
- media type；
- lineage；
- evidence/policy refs。

S3 bucket/key 是 ExternalRef/locator，不是 Artifact ID。

# 26. IdentityAdapter

Baseline：

- authenticate_external_subject
- resolve_subject
- resolve_groups
- group_membership
- claims_snapshot
- health

Authority boundary：

- Principal stable ID 属平台；
- external user/group ID 是 ExternalRef；
- Team 暂保持 external group reference；
- RBAC/Approval/Policy 最终计算属平台；
- Identity Provider 不能 self-grant platform role。

ServiceAccount 是 Principal.kind，而不是 vendor service-account DTO。

# 27. OCIRegistryAdapter

P1-D01 正式落地。

Baseline：

- resolve_manifest
- resolve_digest
- pull
- push
- tags
- attestations
- signatures
- scan_refs
- retention_observe
- health

规则：

- Deployment pin digest；
- mutable tag 不能作为 release Authority；
- Harbor project/repository/tag 只为 ExternalRef；
- signature/SBOM/attestation 作为 Evidence material；
- OCIRegistryAdapter 与 ObjectStorageAdapter 不合并。

# 28. Backend Replacement Protocol

所有 Production Backend 必须具备 Exit Path。

标准替换流程：

~~~text
Replacement candidate
→ C0 Manifest
→ C1 Contract conformance
→ C2 Golden Journey / shadow
→ portability/rebuild proof
→ C3 Production eligibility
→ Human Approval where required
→ bounded cutover
→ verify Northbound + Domain invariants
→ rollback window
→ retire old implementation
~~~

冻结不变量：

1. stable Domain ID 不变；
2. Northbound Contract 不变；
3. business revision 只有业务内容变化才变；
4. ExternalRef 可以变化；
5. old Backend 保留到 rollback window 结束；
6. cutover failure 回旧 LKG；
7. replacement Evidence 不删除旧 Evidence。

这关闭 CG-09 的 Adapter conformance/replacement semantics。

# 29. ExternalRef Migration Mapping

Backend replacement 需要记录：

~~~text
Domain ID
old ExternalRef
new ExternalRef
migration operation
verification Evidence
effective time
rollback ExternalRef
~~~

Mapping 属平台 read model / Evidence，不允许只存在 migration script log。

这收敛 CG-10 的 Adapter-side semantics；Northbound read model 仍需 API extension。

# 30. Observability

每个 Adapter operation 必须传播：

- request_id；
- correlation_id；
- trace context；
- operation_id / workflow_ref；
- adapter_id；
- backend system；
- latency；
- outcome；
- normalized error；
- retry count。

Metrics/log/trace 不能包含 secret plaintext。

# 31. Event Boundary

Adapter **不能直接发布 vendor raw event 作为 Domain Event**。

正确：

~~~text
vendor webhook / poll / SDK result
→ Adapter observation
→ Controller reconciliation
→ State Machine transition
→ Domain Event
~~~

只有 MessagingAdapter 负责 transport P1-03 已规范化 Event。

# 32. Security / Supply Chain

Adapter implementation 进入 C3 前必须有：

- exact source/revision or digest；
- license evidence；
- SBOM；
- vulnerability/security scan；
- config schema；
- secret requirements；
- network boundary；
- egress requirement；
- update/rollback procedure；
- replacement candidate/exit path。

闭源依赖进入关键路径按既有 Governance 规则升级责任等级。

# 33. Contract Gap Closure

本 WP 对 P2-03 Gap 的处理：

- CG-01：Model intake 的 AssetSource/AssetHub implementation boundary **CLOSED**；Northbound intake action 仍待 API extension。
- CG-03：Training checkpoint/resume Adapter operations **CLOSED**。
- CG-06：Knowledge/Index rebuild 的 Vector/Search implementation semantics **CLOSED**；Northbound action 仍待 API extension。
- CG-09：Adapter conformance / backend replacement **CLOSED**。
- CG-10：ExternalRef migration mapping semantics **CLOSED**；read API 待 extension。
- CG-14：Serving rollback primitive 与 LKG boundary **CLOSED at Adapter layer**；Northbound recover action 待 extension。

# 34. Machine-readable Catalog

contracts/adapters/adapter-catalog.v1.json 对每个 Adapter kind 冻结：

- authority_boundary；
- required_operations；
- mutation_operations；
- external_ref_rule；
- secret_policy；
- minimum_conformance。

这是 Contract index，不是 runtime plugin registry。

# 35. Acceptance Criteria

- [x] P1-D01 OCIRegistryAdapter 正式落地。
- [x] P1-D02 AssetSourceAdapter / AssetHubAdapter 正式拆分。
- [x] P1-D04 ProviderAdapter / ServingAdapter 分离且共享 capability conformance。
- [x] 第一批 15 个 Adapter kind 全部定义。
- [x] Common ExecutionContext / Result / Error taxonomy 冻结。
- [x] Retry / idempotency / UNKNOWN reconciliation 冻结。
- [x] timeout/cancellation 能力明确。
- [x] capability negotiation 替代 vendor/version 判断。
- [x] C0-C3 conformance level 冻结。
- [x] Backend Replacement / Exit Path 冻结。
- [x] Secret plaintext 不可穿过普通 Adapter payload。
- [x] vendor raw DTO 不进入 UI/API/Event。
- [x] State Machine 仍是 lifecycle Authority。
- [x] 提供 machine-readable manifest schema + catalog。

# 36. Exit Condition

WP-P1-05 完成。

下一步不是直接大规模编码。应先对 Golden Journey 的剩余 Northbound Gap 做一次 **P1 Contract Closure**，再判断：

- P2-06 Design System Direction；
- P3 Repository Skeleton 是否可启动。

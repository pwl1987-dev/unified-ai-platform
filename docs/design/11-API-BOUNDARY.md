# Northbound API Boundary v1.0

> Work Package：**WP-P1-02 Northbound API Contract**
>
> 状态：**Baseline Frozen for P1 downstream contracts**
>
> Machine-readable baseline：contracts/openapi/unified-ai-platform.v1.json
>
> 上位 Authority：Functional Architecture、Technology Stack、Core Domain Model、P1 Decision Register。

## 1. 为什么存在

Northbound Contract 把 Application / Agent / UI 与可替换 Backend 隔开。调用方只依赖平台稳定语义，不依赖 Qwen、vLLM、SGLang、LiteLLM、GPU 型号、Harbor、MLflow 或任意第三方 DTO。

冻结边界：

~~~text
Application / Agent / Web UI
        ↓
Northbound API
        ↓
Control Hub Domain / Policy / Gate / Approval
        ↓
Adapter Contracts
        ↓
replaceable Backend
~~~

Backend 替换允许改变 ExternalRef、status observation 和 Evidence，但不得要求调用方更换 Domain ID 或重新理解 northbound payload。

## 2. 三个 Plane

### 2.1 AI Data Plane — /v1/*

调用者：Application、Agent、受控 Tool。

目的：调用稳定 Capability。

第一批 surface：

- POST /v1/capabilities/{capability_id}:invoke
- POST /v1/chat/completions
- POST /v1/responses
- POST /v1/embeddings

兼容入口中的 model 字段只接受 stable Capability ID 或平台 capability alias；它不是 vendor model name 的 Authority。

多模态统一通过 content parts / capability invocation 表达，不新增 provider-specific payload。

### 2.2 Control Plane — /api/v1/*

调用者：Web UI、SDK、自动化 Workflow、受控 Agent。

目的：管理平台 Domain Object 与其 lifecycle。

本 baseline 只冻结高价值骨架：

- Capability read / mutation pattern；
- Deployment promotion；
- Training/Evaluation Run creation/query；
- Resource/GPU read model；
- asynchronous Operation；
- Evidence read；
- Project/Principal scope references。

后续对象 CRUD 复制同一 pattern，不为每个对象另造语义。

### 2.3 Admin / Governance Plane — /api/v1/*

调用者：Platform Admin、Security/Auditor、Approver，以及继承其有效权限的受控 Agent。

覆盖：

- Approval；
- Policy / security-sensitive operation；
- dependency risk；
- Provider / Backend onboarding；
- privileged change。

**不存在通用 backend-admin passthrough endpoint。** 高权限操作仍必须映射到平台 Domain Action、Policy、Gate、Approval、Evidence，不能绕过 Adapter。

## 3. Authority 与 Stable Domain ID

Authority 在 Control Hub，不在 Backend。

ID 规则：

- Domain ID：平台生成，创建后不可变。
- ExternalRef：只表示 backend/provider/source 对应物。
- Project：Stage-1 Scope Authority。
- Principal：actor Authority。
- backend object 被替换时 stable Domain ID 保持不变，ExternalRef 可以新增、失效或 supersede。

UI 不允许把 ExternalRef 当路由主键。

## 4. spec / status

所有可变 Domain Resource 坚持：

~~~text
spec   = declared / desired / business revision input
status = observed fact
~~~

客户端 mutation 默认只修改 spec 或触发显式 Action；status 由 Controller/Adapter observation 更新。

不得通过 PATCH status 来伪造成功。

## 5. 同步与异步

同步用于：

- read/list；
- validation；
- bounded query；
- 低延迟 capability invocation；
- 明确能在单请求预算内完成的小 mutation。

异步用于：

- Deployment rollout/promotion；
- Training/Evaluation；
- model/dataset ingest；
- backend replacement；
- restore/recovery；
- 长时资源变更。

异步操作返回 HTTP 202 + OperationReference，至少包含 operation_id、workflow_ref、status、resource_ref 与 correlation_id。调用方通过 GET /api/v1/operations/{operation_id} 获取状态。

Operation 不是第二 Authority；最终业务状态仍回到 Domain Object status + Evidence。

## 6. Resource mutation 与 optimistic concurrency

authoritative object mutation：

1. GET 得到 resource_version；
2. PATCH/Action 发送 If-Match: "<resource_version>"；
3. 服务端只在版本匹配时执行；
4. 冲突返回 412 RESOURCE_VERSION_MISMATCH；
5. 成功后 resource_version 单调增加。

business revision 不参与 If-Match，不与 resource_version 混用。

Create / action mutation 支持 Idempotency-Key。服务端在同一 Principal + Project + operation family 内对 key 去重，重复请求返回原结果或原 OperationReference。

## 7. Pagination / filter / sort

列表统一使用：

- page_token
- page_size，默认 50，最大 200
- filter：受白名单字段约束，不接受任意 SQL/表达式注入
- sort：字段白名单，前缀 - 表示倒序

返回：

- items
- page.next_page_token
- page.total_size 仅在成本可接受时返回

token 是 opaque cursor，客户端不得解析。

## 8. Request / Correlation ID

所有入口接受：

- X-Request-ID：单请求标识，可由客户端提供；服务端校验格式并保证返回。
- X-Correlation-ID：跨请求/Workflow/Agent chain 相关标识。
- trace context：由 OpenTelemetry 传播。

request_id 不等于 idempotency key；correlation_id 不等于 workflow_id。

## 9. Common Error Envelope

所有非 2xx 业务错误使用统一 ErrorEnvelope：

~~~text
error.code
error.message
error.category
error.retryable
error.request_id
error.correlation_id
error.details
error.evidence_refs[]
error.approval_requirement?
error.gate_block?
error.external_refs[]
~~~

关键 error code：

- VALIDATION_FAILED → 400/422
- UNAUTHENTICATED → 401
- POLICY_DENIED / PERMISSION_DENIED → 403
- NOT_FOUND → 404
- RESOURCE_VERSION_MISMATCH → 412
- APPROVAL_REQUIRED → 409
- GATE_BLOCKED → 409
- IDEMPOTENCY_CONFLICT → 409
- RATE_LIMITED → 429
- BACKEND_ERROR → 502
- BACKEND_UNAVAILABLE / CAPABILITY_UNAVAILABLE → 503

Backend 原始错误不能直接透传为平台 contract；可以作为受控 diagnostic ExternalRef / Evidence 记录。

## 10. Evidence

API 默认返回 EvidenceReference，不把大型日志、模型输出、二进制或第三方 trace 全量内联。

EvidenceReference 至少包含：

- evidence_id
- evidence_type
- summary
- produced_at
- immutable_hash 可选
- uri_ref 可选且必须受权限控制

Promotion、Gate、Approval、Run 与故障恢复都必须能追到 Evidence。

## 11. Approval Required

需要人工批准时：

- 若请求尚未执行，返回 409 APPROVAL_REQUIRED；
- ErrorEnvelope 携带 ApprovalRequirement；
- 若系统已生成 Approval Domain Object，返回 approval_id；
- 原请求可以在批准后由同一 workflow/action resume，不要求调用方构造 backend command。

ApprovalRequirement 至少说明：

- responsibility_level
- action
- scope_ref
- environment
- required_role
- approval_id 可选
- expires_at 可选

AI 不得审批自己发起的 Approval。

## 12. Gate Blocked

Gate 未通过时返回 409 GATE_BLOCKED，携带：

- gate_result_id
- gate_name
- state
- failed_checks
- evidence_refs
- retryable_after_new_evidence

禁止通过 API 参数 lower_gate=true、force_pass=true 之类后门改变 Frozen Gate。

## 13. Third-party ExternalRef

ExternalRef 只用于：

- trace；
- backend observation；
- source provenance；
- migration mapping；
- operator diagnostics。

ExternalRef 不能：

- 充当 Domain ID；
- 进入 URL 作为 canonical resource key；
- 决定生命周期；
- 决定 Approval/Gate。

## 14. Secret Boundary

普通 JSON payload 不接受 secret plaintext。

允许：

- secret_ref
- credential_ref
- broker lease reference

Secret plaintext 必须在 SecretAdapter / Secret Broker 的受控执行边界解析，不写日志、不写 Evidence、不进入 Agent prompt。

如果 capability 需要 secret，northbound payload 只声明 SecretRef。

## 15. Versioning / Compatibility

- AI Data Plane：/v1/*。
- Control/Admin Plane：/api/v1/*。
- schema_version 处理 Domain payload schema。
- API minor additive change 不改 URL major version。
- 删除字段、改变语义、收紧到不兼容输入必须进入新的 major version 或兼容迁移期。
- 未知可选 response 字段客户端应忽略；服务端不得依赖客户端认识新字段。
- enum 扩展在 generated client 中必须使用 unknown-safe 策略。

## 16. SDK Generation

OpenAPI 3.1 baseline 必须可生成：

- TypeScript client；
- Go client；
- Python client。

Generated SDK 不是 Authority；OpenAPI + Contract Tests 是 Authority。

P3 Contract CI 至少验证：

1. OpenAPI parse；
2. operationId 唯一；
3. TypeScript / Go / Python generation smoke；
4. generated client compile/import smoke；
5. backward compatibility diff；
6. common headers/error types 一致。

## 17. Capability Invocation Contract

调用方选择 Capability，而不是 Backend。

请求包含：

- input / content parts；
- parameters；
- response_mode；
- constraints：latency/cost/privacy/quality 等可选约束；
- metadata：仅业务可审计元数据，不放 secret。

平台负责在 Policy 下选择 Provider / Deployment / Runtime，并返回：

- output；
- capability_id；
- selected implementation 只作为 execution metadata；
- usage；
- evidence_refs；
- request/correlation ID。

Backend 被替换时请求 contract 不变。

## 18. Deployment Promotion Contract

Promotion 是显式 Action，不等于 PATCH status=production。

输入：

- target_environment；
- candidate revision；
- expected resource_version；
- gate_result_id；
- rollout policy；
- rollback/LKG ref。

可能结果：

- 202 OperationReference；
- 409 APPROVAL_REQUIRED；
- 409 GATE_BLOCKED；
- 412 RESOURCE_VERSION_MISMATCH。

成功后才由 Controller 更新 Deployment status，并产生 Evidence。

## 19. Run Creation / Query

POST /api/v1/runs 创建 TrainingRun / EvaluationRun，返回 202。

Run spec 保存业务 revision/pinned inputs，不把 runtime job ID 当 Run ID。

GET /api/v1/runs/{run_id} 返回：

- stable run_id；
- spec/status；
- operation/workflow refs；
- progress；
- evidence_refs；
- external_refs。

## 20. Resource / GPU Read Model

GET /api/v1/resources/gpus 是 read model，不是 GPU canonical mutation endpoint。

允许聚合：

- node/gpu stable ID；
- inventory；
- allocation；
- health；
- utilization；
- temperature/power；
- active workload refs；
- observed_at。

vendor telemetry 字段只能进入 namespaced diagnostics 或 ExternalRef，不上浮为通用 Authority。

## 21. AI Operator 调用约束

AI Operator 使用与 Web UI 相同的 Northbound API，不拥有特殊后门。

每个有副作用调用必须带 effective execution context：

- Acting as Principal；
- Project Scope；
- Environment；
- Responsibility Level；
- Proposed Action；
- Evidence destination；
- Gate；
- Approval；
- Rollback/LKG。

Command Palette 同样不能绕过这些约束。

## 22. Acceptance Criteria

- [x] /v1 与 /api/v1 plane 分离。
- [x] Data Plane 绑定 Capability，不绑定 Model/Runtime/Provider/GPU。
- [x] Stable Domain ID 与 ExternalRef 分离。
- [x] spec/status 分离。
- [x] async Operation / Workflow reference 冻结。
- [x] resource_version / If-Match / 412 冻结。
- [x] page/filter/sort/idempotency/correlation 规则明确。
- [x] Error/Page/Operation/Evidence/Approval/Gate common contract 已进入 OpenAPI。
- [x] Secret plaintext 禁止进入普通 payload。
- [x] OpenAPI 3.1 可用于 TS/Go/Python client generation。
- [x] Backend replacement 不改变 Northbound Contract。
- [x] P1-D01~D06 已进入独立 Decision Register。

## 23. 本 WP 不做什么

- 不一次性设计所有 Domain CRUD；
- 不冻结 Event Contract；
- 不冻结完整 State Machine；
- 不冻结所有 Adapter method；
- 不进入产品编码；
- 不运行 Phase 06 Benchmark；
- 不修改 eval/vllm/nextgen-20260917/**。

下一步由 WP-P2-03 Golden Journeys 反向验证 Contract Gap / Orphan API Risk。


# 24. Golden Journey Contract Closure Amendment — OpenAPI 0.2

WP-P2-03 暴露的 CG-01~CG-15 已由 P1-03 / P1-04 / P1-05 与本次 additive API extension 收敛。

新增 northbound family：

- ModelAsset / DatasetAsset intake + detail；
- Experiment create/detail；
- Knowledge Index rebuild；
- TrainingRun checkpoint/resume；
- Policy read/mutate；
- UpstreamDependency read/migration；
- Adapter replacement / ExternalRef migration mapping；
- Approval request / Decision Packet read；
- Deployment detail / recover-to-LKG；
- Incident recovery read projection。

详细闭合证据见：

- docs/design/16-P1-CONTRACT-CLOSURE.md

约束保持：

1. 不提供 backend-admin passthrough；
2. 不提供 AI Operator 特权 endpoint；
3. 不允许 direct PATCH status；
4. 所有 mutation 仍受 State Machine / Policy / Gate / Approval；
5. Incident 当前只做 read-only projection；
6. Scheduler preemption 保持内部 Policy action，不暴露任意手工抢占 API。

# 25. P1-02 Closure Acceptance

- [x] Golden Journey CG-01~CG-15 均有 Northbound / Event / State / Adapter owner。
- [x] OpenAPI 保持 3.1。
- [x] 仍是 additive、task-driven surface，不是全量 CRUD。
- [x] P3 Contract CI 可以以本文件 + OpenAPI 0.2 为 baseline。

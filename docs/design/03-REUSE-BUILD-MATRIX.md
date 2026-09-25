# Reuse / Build Matrix v0.1

> Work Package: **WP-P0-01 — Reuse / Build Matrix**  
> Status: **FIRST PASS FROZEN FOR P1/P2 INPUT**  
> Authority: `docs/design/00-FUNCTIONAL-ARCHITECTURE.md`, `docs/design/01-TECHNOLOGY-STACK.md`, `docs/design/02-WORK-BREAKDOWN.md`  
> Evidence date: **2026-09-25**  
> Scope: 只做复用/自建/Adapter/退出路径决策，不引入产品代码，不改变 Frozen Architecture。

---

## 1. 决策规则

所有第三方能力必须遵守：

```text
Our Domain Contract
        ↓
Our Adapter / Boundary
        ↓
Third-party Backend
```

判定值仅允许：

- **REUSE**：直接复用为基础设施实现，但不让其拥有平台业务语义。
- **EXTEND**：在清晰上游边界内扩展，扩展仍可被替换。
- **ADAPTER**：第三方只通过我方 Adapter 接入。
- **BUILD**：核心语义/Authority 必须由平台自建。
- **REPLACE_LATER**：Stage-1 先采用较轻实现或不引入专用组件，出现 Evidence 后再替换/升级。
- **RESTRICTED**：可受限使用，必须满足额外 License/Security/Operational Gate。
- **REJECT**：当前阶段不采用。

自主替代优先级：

- **P0**：立即避免形成依赖或需要尽快准备替换。
- **P1**：核心路径，高优先级保持双实现/可替代能力。
- **P2**：中期替代能力。
- **P3**：低优先级，保持数据/协议可迁移即可。

### Authority 红线

第三方不得成为以下对象的唯一 Authority：

- Domain ID / lifecycle / ownership / lineage；
- Production Promotion / Gate / Approval；
- Policy / Permission / Security Exception；
- Canonical Evidence；
- Capability / Deployment 的平台级状态；
- Northbound API 语义；
- Agent 可以做什么、谁批准、何时回滚的最终判定。

---

## 2. 总矩阵

| 候选 | 决策 | Stage-1 角色 | License / 风险摘要 | Authority 风险 | 自主替代优先级 |
|---|---|---|---|---|---|
| CSGHub | **ADAPTER** | Asset Hub Backend candidate | Apache-2.0 | 中：资产/权限/状态不能反向定义平台 | P2 |
| MLflow | **ADAPTER** | Experiment / Tracking / Artifact metadata backend | Apache-2.0 | 中高：Run/Model Registry 状态不可成为平台 Gate | P1 |
| BentoML | **ADAPTER** | Generic AI/ML serving backend | Apache-2.0 | 中：Serving DTO/Deployment 状态不可上浮 | P2 |
| ModelScope | **ADAPTER** | Model/Dataset source | Apache-2.0 | 低中：外部 ID 不能成为稳定 Domain ID | P2 |
| ms-swift | **ADAPTER** | Training/Fine-tuning backend | Apache-2.0 | 中：训练状态与产物须回写我方 Contract | P2 |
| SGLang | **ADAPTER** | LLM/VLM runtime | Apache-2.0 | 中：Runtime 私有参数不能成为 northbound contract | P1 |
| vLLM | **ADAPTER** | LLM/VLM runtime | Apache-2.0 | 中 | P1 |
| llama.cpp | **ADAPTER** | CPU/edge/GGUF runtime | MIT | 中 | P2 |
| LiteLLM OSS / alternatives | **ADAPTER** | Provider/Gateway implementation candidate | MIT core；`enterprise/` 独立许可 | **高**：Gateway 最接近 Northbound Authority | **P1** |
| PostgreSQL | **REUSE** | Canonical transactional state store | PostgreSQL License | 低：Authority 在我方 schema/contract，不在扩展私有语义 | P3 |
| S3-compatible / MinIO | **RESTRICTED** | Object storage implementation candidate | MinIO AGPL-3.0；官方 GitHub repo 当前 archived | 中高：对象格式/生命周期/SDK lock-in | **P0** |
| NATS + JetStream | **REUSE** | Event transport / durable stream | Apache-2.0 | 中：事件总线不是最终业务 Authority | P2 |
| OpenBao | **ADAPTER** | Secret backend candidate | MPL-2.0 | 高：Secret storage 可在后端，但策略与审批归平台 | P2 |
| Harbor | **ADAPTER** | OCI registry candidate | Apache-2.0 | 中 | P2 |
| Caddy | **REUSE** | Edge/TLS candidate | Apache-2.0 | 低：仅边缘实现 | P3 |
| libvirt | **ADAPTER** | KVM/QEMU virtualization backend | C API LGPL-2.1+；部分非库代码 GPL-2.0+ | 中：VM 生命周期经 VirtualizationAdapter | P2 |
| Vector DB | **REPLACE_LATER** | Stage-1 优先 PostgreSQL + pgvector；Qdrant candidate | pgvector PostgreSQL License；Qdrant Apache-2.0 | 中高：Index 不能成为 Knowledge Authority | P1 |
| Search Engine | **REPLACE_LATER** | Stage-1 优先 PostgreSQL FTS；OpenSearch candidate | OpenSearch Apache-2.0 | 中高：索引必须可重建 | P1 |
| Workflow Engine | **BUILD** | Core workflow semantics in Go Control Hub；Temporal 仅后续 candidate | Temporal MIT | **极高**：Workflow/Gate/Approval 不外包 | **P0** |

> License 结论是工程准入初判，不替代正式法务审核。正式引入时由 WP-P0-02 固定 exact revision、license hash、SBOM 与 notice。

---

## 3. 逐项八问

### 3.1 CSGHub — ADAPTER

1. **复用哪部分**：模型/数据集/代码类资产发现、仓库/Hub 后端能力、已有生态连接。
2. **不复用哪部分**：平台用户权限、Approval、Gate、生命周期、稳定 Domain ID、Production 状态。
3. **License**：`OpenCSGs/csghub` 当前为 Apache-2.0，工程准入可接受。
4. **数据归谁**：Canonical Asset metadata/lineage 在我方 PostgreSQL；大对象在我方 S3-compatible store 或保留可验证外部引用。
5. **Authority 是否外泄**：禁止。CSGHub 状态仅作为 `UpstreamDependency` / source observation。
6. **Adapter 边界**：`AssetHubAdapter`：discover / resolve / fetch / publish-mirror / health；返回我方 DTO。
7. **Exit Path**：导出 source URI、digest、license、metadata；切换 Hugging Face/ModelScope/自建 Asset Hub adapter。
8. **自主替代优先级**：P2。

### 3.2 MLflow — ADAPTER

1. **复用哪部分**：experiment tracking、metrics/params/artifact tracking、现成生态。
2. **不复用哪部分**：平台 `Experiment` / `EvaluationRun` / `Evidence` / `GateResult` 的最终状态与 Promotion。
3. **License**：`mlflow/mlflow` 当前 Apache-2.0，可接受。
4. **数据归谁**：关键实验摘要、hash、lineage、Gate evidence 必须回写我方 canonical store；artifact 进入我方 object storage。
5. **Authority 是否外泄**：高风险点是把 MLflow Run/Model Registry 状态误当平台生命周期；明确禁止。
6. **Adapter 边界**：`ExperimentAdapter`，仅负责 create/log/query/link/export，不暴露 MLflow DTO 到 UI/API。
7. **Exit Path**：Experiment/Evidence schema 可导出；artifact 独立；可替换为自建 tracking 或其他 backend。
8. **自主替代优先级**：P1。

### 3.3 BentoML — ADAPTER

1. **复用哪部分**：通用模型服务封装、worker/serving、已有模型生态接入。
2. **不复用哪部分**：Unified Gateway、平台 Deployment Authority、Policy/Gate、全局调度。
3. **License**：`bentoml/BentoML` 当前 Apache-2.0，可接受。
4. **数据归谁**：Deployment spec、image/artifact digest、capability registration 归我方。
5. **Authority 是否外泄**：不得让 BentoML deployment state 直接成为平台 Production 状态。
6. **Adapter 边界**：`ServingAdapter`；deploy / stop / health / endpoints / evidence collection。
7. **Exit Path**：同一 Deployment Contract 可切换 SGLang/vLLM/custom OCI serving。
8. **自主替代优先级**：P2。

### 3.4 ModelScope — ADAPTER

1. **复用哪部分**：模型/数据集来源、下载、生态 metadata。
2. **不复用哪部分**：本地 Model Registry、License Gate、Production lifecycle。
3. **License**：`modelscope/modelscope` 当前 Apache-2.0，可接受。
4. **数据归谁**：下载后的 artifact、digest、source attribution、license evidence 归我方。
5. **Authority 是否外泄**：外部 source ID 只能是 alias，不能替代稳定 `ModelAsset.id`。
6. **Adapter 边界**：`AssetHubAdapter` / source connector。
7. **Exit Path**：source URI + digest + manifest 可重放；可切换其他模型源。
8. **自主替代优先级**：P2。

### 3.5 ms-swift — ADAPTER

1. **复用哪部分**：SFT/LoRA/训练编排、ModelScope 生态训练能力。
2. **不复用哪部分**：平台 TrainingRun lifecycle、scheduler、budget、Gate。
3. **License**：`modelscope/ms-swift` 当前 Apache-2.0，可接受。
4. **数据归谁**：训练配置快照、dataset revision、checkpoint digest、metrics/evidence 归我方。
5. **Authority 是否外泄**：不得以 ms-swift 内部 task/run state 作为我方最终状态。
6. **Adapter 边界**：`TrainingAdapter`；render job / start / observe / cancel / resume / collect outputs。
7. **Exit Path**：训练 Contract 与 checkpoint/export format 独立，可接 TRL/Transformers/自建 worker。
8. **自主替代优先级**：P2。

### 3.6 SGLang — ADAPTER

1. **复用哪部分**：高性能 LLM/VLM inference runtime。
2. **不复用哪部分**：逻辑模型名、Capability routing、Production Gate、全局 scheduler。
3. **License**：`sgl-project/sglang` 当前 Apache-2.0，可接受。
4. **数据归谁**：runtime config snapshot、image digest、benchmark evidence 归我方。
5. **Authority 是否外泄**：runtime endpoint/CLI 参数仅属 Adapter implementation detail。
6. **Adapter 边界**：`ServingAdapter` + Runtime plugin contract。
7. **Exit Path**：同一 Capability/Deployment 可切换 vLLM/BentoML/其他 runtime。
8. **自主替代优先级**：P1。

### 3.7 vLLM — ADAPTER

1. **复用哪部分**：高性能 LLM/VLM serving/runtime。
2. **不复用哪部分**：平台 Gateway、Capability、Gate、scheduler semantics。
3. **License**：`vllm-project/vllm` 当前 Apache-2.0，可接受。
4. **数据归谁**：runtime config、benchmark、deployment evidence 归我方。
5. **Authority 是否外泄**：不得。
6. **Adapter 边界**：与 SGLang 同一 `ServingAdapter` / runtime contract。
7. **Exit Path**：同 Contract 切换 SGLang/BentoML/其他 OCI runtime。
8. **自主替代优先级**：P1。

### 3.8 llama.cpp — ADAPTER

1. **复用哪部分**：GGUF、CPU/异构/边缘 inference、轻量 server。
2. **不复用哪部分**：统一 API 语义、Capability routing、平台 deployment lifecycle。
3. **License**：`ggml-org/llama.cpp` 当前 MIT，可接受。
4. **数据归谁**：模型 artifact、conversion provenance、benchmark evidence 归我方。
5. **Authority 是否外泄**：不得。
6. **Adapter 边界**：`ServingAdapter` / runtime plugin。
7. **Exit Path**：Capability 不依赖 GGUF/llama.cpp 专用 DTO。
8. **自主替代优先级**：P2。

### 3.9 LiteLLM OSS / alternatives — ADAPTER

1. **复用哪部分**：Provider protocol normalization、部分 routing/provider integration。
2. **不复用哪部分**：平台 Northbound Contract、最终 Provider selection policy、budget/security authority。
3. **License**：`BerriAI/litellm` 根 LICENSE 明确：核心 MIT；`enterprise/` 如存在则使用独立许可。Stage-1 只允许 OSS 边界，企业目录必须单独 Gate。
4. **数据归谁**：Provider config metadata、routing evidence、usage ledger 归我方；secret 不进入业务数据库。
5. **Authority 是否外泄**：**高风险**。UI/业务绝不直接绑定 LiteLLM DTO、virtual key、team 或 routing 状态。
6. **Adapter 边界**：`ProviderAdapter`；normalize request/response/errors/usage/health。
7. **Exit Path**：Provider contract + conformance tests；并行验证至少一个替代 adapter。
8. **自主替代优先级**：P1。

### 3.10 PostgreSQL — REUSE

1. **复用哪部分**：事务、约束、查询、migration、canonical relational state。
2. **不复用哪部分**：不把业务语义藏进不可移植扩展/存储过程；不把 DB 当 workflow engine。
3. **License**：PostgreSQL License，宽松，可接受。
4. **数据归谁**：平台拥有 schema、migration、backup、export；DB 只是实现。
5. **Authority 是否外泄**：低；核心 Authority 正式落在我方 schema/contract。
6. **Adapter 边界**：Repository/Data Access boundary；对上层暴露 Domain Repository，不暴露 vendor-specific DTO。
7. **Exit Path**：SQL dump + logical export + documented schema/migrations；恢复演练必须可重建。
8. **自主替代优先级**：P3。

### 3.11 S3-compatible / MinIO — RESTRICTED

1. **复用哪部分**：只复用 S3-compatible object API 形态；MinIO 仅作为受限候选实现。
2. **不复用哪部分**：MinIO-specific admin/identity/lifecycle semantics 不进入 Domain Contract。
3. **License**：`minio/minio` 当前 AGPL-3.0，且 GitHub repository 当前标记 **archived**。因此不得把它作为无替代路径的长期默认。
4. **数据归谁**：对象、manifest、digest、retention policy 的 Authority 归平台；bucket 只是存储实现。
5. **Authority 是否外泄**：禁止 object-store-specific state 成为唯一 artifact registry。
6. **Adapter 边界**：`ObjectStorageAdapter`，只依赖 S3-compatible operations + capability probe。
7. **Exit Path**：对象可逐 bucket/manifest 迁移到 Ceph RGW、Garage、云 S3 或其他兼容实现；禁止 proprietary metadata lock-in。
8. **自主替代优先级**：**P0**。在 P4 选型前完成替代候选 bakeoff，不默认锁定 MinIO。

### 3.12 NATS + JetStream — REUSE

1. **复用哪部分**：event transport、durable stream、consumer、replay。
2. **不复用哪部分**：最终业务状态、Approval/Gate Authority、不可重建的唯一事实。
3. **License**：`nats-io/nats-server` 当前 Apache-2.0，可接受。
4. **数据归谁**：事件 schema、idempotency、correlation、retention 由平台定义；canonical state 回到 PostgreSQL。
5. **Authority 是否外泄**：禁止“队列里有消息”成为唯一任务状态。
6. **Adapter 边界**：`MessagingAdapter` + Frozen Event Contract。
7. **Exit Path**：事件 envelope 与业务 handler 独立；可替换其他 broker。
8. **自主替代优先级**：P2。

### 3.13 OpenBao — ADAPTER

1. **复用哪部分**：secret storage、lease/rotation、动态凭据能力。
2. **不复用哪部分**：平台权限模型、审批、secret 使用政策、业务角色。
3. **License**：`openbao/openbao` 当前 MPL-2.0，可接受，但修改/分发需按 MPL 要求处理。
4. **数据归谁**：secret value 可由 Secret Backend 保管；secret metadata/policy binding/audit reference 归平台。
5. **Authority 是否外泄**：高风险点是把 OpenBao policy 直接当平台 RBAC；禁止。
6. **Adapter 边界**：`SecretAdapter`：put/get/lease/revoke/rotate/health，不向 UI 暴露后端内部 token。
7. **Exit Path**：secret logical name 与 backend path 解耦；迁移 runbook + rotation。
8. **自主替代优先级**：P2。

### 3.14 Harbor — ADAPTER

1. **复用哪部分**：OCI image/artifact registry、replication/scanning ecosystem。
2. **不复用哪部分**：平台 Artifact Authority、Promotion/Gate、业务 RBAC。
3. **License**：`goharbor/harbor` 当前 Apache-2.0，可接受。
4. **数据归谁**：image digest、SBOM、signature/evidence、promotion record 归平台。
5. **Authority 是否外泄**：Harbor project/tag 不得成为平台 lifecycle。
6. **Adapter 边界**：需要明确 OCI Registry contract；详见 §5 P1 裁决项。
7. **Exit Path**：OCI Distribution API + digest immutable reference，可迁移其他 registry。
8. **自主替代优先级**：P2。

### 3.15 Caddy — REUSE

1. **复用哪部分**：Edge、TLS、reverse proxy、基础路由。
2. **不复用哪部分**：业务鉴权/Policy/Capability routing 的核心语义。
3. **License**：`caddyserver/caddy` 当前 Apache-2.0，可接受。
4. **数据归谁**：路由意图与证书/域名配置声明由平台/IaC 管理。
5. **Authority 是否外泄**：低；Caddy 是执行层。
6. **Adapter 边界**：Stage-1 不新增复杂 Edge abstraction；使用可生成、可替换的 declarative config。
7. **Exit Path**：标准 HTTP/TLS/upstream semantics，可迁移 Nginx/Envoy/HAProxy 等。
8. **自主替代优先级**：P3。

### 3.16 libvirt — ADAPTER

1. **复用哪部分**：KVM/QEMU virtualization control、成熟稳定 API。
2. **不复用哪部分**：平台 VM lifecycle semantics、placement、Approval、Resource Authority。
3. **License**：libvirt C API LGPL-2.1-or-later；部分非 C library 代码 GPL-2.0-or-later。作为系统组件/外部 API 使用可接受，vendoring/modification 必须逐文件复核。
4. **数据归谁**：VM desired state、identity、resource allocation、lineage 归平台。
5. **Authority 是否外泄**：libvirt UUID 作为 backend identifier，不替代我方稳定 `VM.id`。
6. **Adapter 边界**：`VirtualizationAdapter`。
7. **Exit Path**：同 Contract 接 VMware/Proxmox/Incus；backend IDs 存 alias mapping。
8. **自主替代优先级**：P2。

### 3.17 Vector DB — REPLACE_LATER

1. **复用哪部分**：Stage-1 优先复用 PostgreSQL + pgvector；需要专用能力时首批 bakeoff 可含 Qdrant。
2. **不复用哪部分**：KnowledgeAsset/Index lifecycle、source lineage、embedding policy、ACL。
3. **License**：pgvector 为 PostgreSQL License；`qdrant/qdrant` 当前 Apache-2.0。
4. **数据归谁**：source chunks、embedding recipe、index manifest 归平台；向量 index 视为可重建派生物。
5. **Authority 是否外泄**：**Index 永远不是 Knowledge Authority**。
6. **Adapter 边界**：`VectorAdapter`：upsert/query/delete/rebuild/capability probe。
7. **Exit Path**：从 canonical chunks + embedding recipe 重建到任意 vector backend。
8. **自主替代优先级**：P1。

### 3.18 Search Engine — REPLACE_LATER

1. **复用哪部分**：Stage-1 先用 PostgreSQL FTS/trigram；出现规模/查询能力 Evidence 后评估 OpenSearch。
2. **不复用哪部分**：Document/Knowledge lifecycle、ACL、source truth。
3. **License**：`opensearch-project/OpenSearch` 当前 Apache-2.0。
4. **数据归谁**：索引是派生物；canonical document/chunk/metadata 归平台。
5. **Authority 是否外泄**：搜索引擎不可成为唯一数据存储。
6. **Adapter 边界**：`SearchAdapter`。
7. **Exit Path**：full rebuild from canonical source；query contract 使用我方 schema。
8. **自主替代优先级**：P1。

### 3.19 Workflow Engine — BUILD

1. **复用哪部分**：Stage-1 不引入第二套 workflow authority；Temporal 只作为未来 durability backend candidate。
2. **不复用哪部分**：Goal/Workflow/Approval/Gate/Recovery 的平台语义全部不能外包。
3. **License**：`temporalio/temporal` 当前 MIT，可接受；但“License 可接受”不等于“架构上应立即引入”。
4. **数据归谁**：Workflow desired/current state、step evidence、approval、lease/fencing 归平台。
5. **Authority 是否外泄**：**绝不允许**。这是 WP-P1/P7 的核心 Authority。
6. **Adapter 边界**：`WorkflowAdapter` 只允许把我方 workflow plan 映射到外部 execution backend。
7. **Exit Path**：Stage-1 Go Control Hub + PostgreSQL + NATS 已能保持核心语义；未来 Temporal 只是可插拔执行器。
8. **自主替代优先级**：**P0**（不是“替换 Temporal”，而是优先确保 workflow semantics 自主）。

---

## 4. Stage-1 组合结论

第一轮默认组合收敛为：

```text
Core Authority
  Go Control Hub
  + PostgreSQL
  + Our Domain / API / Event / Gate / Adapter Contracts

Execution / Integration
  CSGHub          via AssetHubAdapter
  MLflow          via ExperimentAdapter
  BentoML         via ServingAdapter
  ModelScope      via Asset source adapter
  ms-swift        via TrainingAdapter
  SGLang/vLLM     via ServingAdapter
  llama.cpp       via ServingAdapter
  LiteLLM/alt     via ProviderAdapter

Infrastructure
  PostgreSQL      REUSE
  NATS/JetStream  REUSE
  Caddy           REUSE
  libvirt         via VirtualizationAdapter
  OpenBao         via SecretAdapter
  Harbor          via OCI Registry contract (P1 clarification required)

Deferred by evidence
  Dedicated Vector DB
  Dedicated Search Engine
  Dedicated Workflow Engine

Restricted
  MinIO as long-term default implementation
```

---

## 5. P1 裁决登记（P1 已收敛）

本 WP 当时登记的 Contract 问题现已由 `docs/design/12-DECISION-REGISTER.md` 与 `docs/design/15-ADAPTER-CONTRACT.md` 正式收敛。以下保留原始问题与最终结果，避免历史文档继续显示“未裁决”：

### P1-D01 — OCI Registry Adapter naming

现有技术栈冻结了 Harbor candidate，WP-P1-05 首批 Adapter 列表却没有显式的 `OCIRegistryAdapter` / `RegistryAdapter`。

**最终结果：RESOLVED — 使用 `OCIRegistryAdapter`。** `ObjectStorageAdapter` 不覆盖 OCI distribution / manifest / digest / signature / retention 语义。

验收要求保持：UI、Deployment、SBOM、Promotion 不直接绑定 Harbor DTO。

### P1-D02 — AssetHubAdapter source/publish responsibilities

**最终结果：RESOLVED — 拆分 `AssetSourceAdapter` 与 `AssetHubAdapter`。**

- AssetSourceAdapter：discover / resolve / metadata / license / provenance / fetch；
- AssetHubAdapter：mirror / publish / catalog / replication / retention；
- 同一 Backend 可以同时实现两者，但 Conformance 独立。

目标保持：避免“发现/下载”和“内部资产发布/治理”混成一个 Authority。

### P1-D03 — Derived Index rule

**最终结果：RESOLVED — Index 仍是可重建派生物，不是 Knowledge/Data Authority。**

`Index` 必须冻结为可重建派生物，并记录：

- source revision；
- embedding/search recipe；
- backend；
- backend version；
- build evidence；
- rebuild status。

避免 Vector/Search backend 成为知识唯一事实源。

### P1-D04 — Gateway conformance boundary

**最终结果：RESOLVED — ProviderAdapter / ServingAdapter 分离，共享最小 Capability Conformance。**

`ProviderAdapter` 与 `ServingAdapter` 必须共享最小 conformance suite，但不能混为一个 Adapter：

- Provider = 外部/异构 API 能力；
- Serving = 我方可控 runtime/deployment；
- Northbound `/v1` 永远由平台定义。

---

## 6. Acceptance Criteria

WP-P0-01 只有同时满足以下条件才算完成：

- [x] 覆盖 WBS 指定的 19 类候选；
- [x] 每项给出唯一主判定；
- [x] 每项回答“复用/不复用/License/数据/Authority/Adapter/Exit Path/自主替代优先级”八问；
- [x] 明确 Core Authority 不外泄；
- [x] 明确 MinIO 当前 AGPL + archived 风险，不把它锁为长期默认；
- [x] 明确 LiteLLM OSS/enterprise license boundary；
- [x] Vector/Search index 定义为可重建派生物；
- [x] Workflow semantics 保持 BUILD，不新增第二 Authority；
- [x] P1 缺口只登记，不反向修改 Frozen Architecture。

---

## 7. WP-P0-02 输入

下一包 `WP-P0-02 — Third-party Dependency Register` 需要把本文件的“候选级决策”转为机器可核验依赖清单，至少固定：

```text
exact repo
exact revision/tag
license
license hash
SBOM
security advisories
upstream health
mirror policy
replacement candidate
owner
review date
```

WP-P0-02 不得改变本文件的 Authority 原则；如需改变主判定，必须形成带 Evidence 的 Architecture/Dependency Change。

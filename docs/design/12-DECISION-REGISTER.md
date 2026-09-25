# P1 Decision Register v1.0

> 状态：**Normative / WP-P1-02**
>
> 生效日期：2026-09-25
>
> 上位 Authority：
> - docs/design/00-FUNCTIONAL-ARCHITECTURE.md
> - docs/design/01-TECHNOLOGY-STACK.md
> - docs/design/10-DOMAIN-MODEL.md
> - docs/design/03-REUSE-BUILD-MATRIX.md
>
> 规则：本文件记录 P1 的显式裁决。实现、UI、Adapter 或第三方 Backend 不得通过局部便利反向修改这些结论。

## P1-D01 — OCI Registry Adapter naming

**Status：RESOLVED**

**Decision：** 新增并统一使用 **OCIRegistryAdapter**。ObjectStorageAdapter 只处理对象存储语义，不能代替 OCI distribution / manifest / digest / signature / retention 语义。

**Authority：** Control Hub 持有 Artifact、Deployment、Promotion、SBOM 与 Gate 语义；Harbor 只是 OCIRegistryAdapter 的候选实现。

**Consequence：** UI/API 不出现 Harbor project/tag 作为 Domain ID；Deployment 必须 pin digest；替换 Harbor 不改变 northbound contract。

**Revisit Trigger：** 只有 OCI distribution 已无法覆盖平台所需 artifact distribution contract，且有 Evidence 证明必须扩展通用 Registry abstraction。

## P1-D02 — AssetSourceAdapter vs AssetHubAdapter

**Status：RESOLVED**

**Decision：** 拆分。

- **AssetSourceAdapter**：discover / resolve / fetch / metadata / license / provenance；适合 ModelScope、Hugging Face 类外部来源。
- **AssetHubAdapter**：mirror / publish / managed catalog / replication / retention；适合 CSGHub 或未来内部 Hub。
- 同一 Backend 可以同时实现两个 Adapter，但两个 Contract 不合并。

**Authority：** ModelAsset / DatasetAsset stable ID、business revision、Gate、Approval 与 lineage 始终属于 Control Hub。

**Revisit Trigger：** 若长期 Evidence 证明两个 contract 的 conformance surface 完全相同且拆分只产生重复，不得仅因一个产品同时支持二者就合并。

## P1-D03 — Index is reconstructable derivative

**Status：RESOLVED / REAFFIRMED**

**Decision：** Index 是可重建派生物，不是 KnowledgeAsset / DatasetAsset Authority。Index 丢失可触发 rebuild，不允许造成 canonical source 丢失。

**Revisit Trigger：** 无普通实现级触发；属于 Domain invariant。

## P1-D04 — Provider vs Serving conformance boundary

**Status：RESOLVED**

**Decision：** ProviderAdapter 与 ServingAdapter 保持分离。

- **ProviderAdapter**：调用外部/异构 AI endpoint，标准化 invoke / stream / usage / error / health。
- **ServingAdapter**：控制我方可管理的 deployment/runtime，标准化 deploy / observe / stop / endpoint / rollout evidence。
- 两者共享最小 Capability Conformance：input modalities、output contract、streaming、usage、error taxonomy、health/readiness、trace correlation。

**Authority：** Capability 是 northbound semantic；Provider、Runtime、Deployment 都不能成为调用方必须绑定的稳定接口。

**Revisit Trigger：** 只有 conformance evidence 证明边界无法表达新的执行形态，并且修改不会让 Backend 获得 Domain Authority。

## P1-D05 — Scope / Identity primitives

**Status：RESOLVED**

**Decision：**

1. **Project** 升格为一等 Domain Object，是 Stage-1 最小稳定 Scope Authority。
2. **Principal** 升格为一等 Domain Object，是 audit / RBAC / Approval / Agent acting-as 的稳定 actor primitive。
3. **ServiceAccount** 不新增一级对象，表示为 Principal.kind = SERVICE_ACCOUNT。
4. **Team** 暂不新增一级对象，通过 IdentityAdapter group reference + ExternalRef 参与授权。
5. **Workspace** 是 UX / task composition，不持有 Domain Authority。
6. **Tenant** Stage-1 暂不引入；真正多租户隔离出现前不预建第二套 scope hierarchy。

**Why：** ownership、RBAC、Approval separation、scope isolation、API consistency 与 Agent authority 都需要平台稳定 ID；但 Stage-1 没有足够 Evidence 支持 Tenant/Workspace/Team 全部对象化。

**Agent Rule：** 每个有副作用的 Agent 动作必须解析 effective Principal + Project Scope + Environment + Policy；Agent 不得 self-escalate 或 self-approve。

**Revisit Trigger：** 多组织隔离、独立计费/密钥域/数据域或法规边界要求真正 Tenant semantics。

## P1-D06 — business revision vs resource_version

**Status：RESOLVED / REAFFIRMED**

**Decision：**

- **resource_version**：Control Hub authoritative mutation/concurrency version，单调递增，用于 If-Match / optimistic concurrency。
- **business revision**：Model/Dataset/Environment/Policy 等业务内容的逻辑修订，属于 spec/asset lineage，可 immutable/pinned。

二者不得复用同一字段，不得因为 backend observation 自动改变 business revision。

**Revisit Trigger：** 无普通实现级触发；属于 concurrency/versioning invariant。

## Acceptance

- [x] D01-D06 均有明确 Status / Decision / Authority / Consequence 或 Revisit Trigger。
- [x] 没有第三方产品获得 Domain Authority。
- [x] D05 只增加满足 scope/identity 必需的最小对象集。
- [x] D06 保持 business revision 与 concurrency version 分离。

# Third-party Dependency Register v0.1

> Work Package: **WP-P0-02 — Third-party Dependency Register**  
> Status: **AUDIT SNAPSHOT / NOT A PRODUCTION VERSION LOCK**  
> Evidence date: **2026-09-25**  
> Upstream Authority: `docs/design/03-REUSE-BUILD-MATRIX.md`  
> Purpose: 把候选级 Reuse/Build 判断转成可审计的第三方依赖登记，为后续 P4/P5 exact-version selection、SBOM、Mirror、Security Gate 和 Replacement Drill 提供输入。

---

## 1. 本登记表是什么

本文件记录两类 pin：

```text
Audit Snapshot Pin
= 2026-09-25 核对上游时观察到的 exact commit

Deployment Pin
= 真正进入 P4/P5 后，通过 compatibility/security/license gate
  选定的 exact tag / commit / image digest
```

**二者不能混用。**

本文件中的 commit SHA 证明“本次设计判断看的是哪一版上游”，不代表 Stage-1 将直接部署该 `main/master` HEAD。

正式进入运行环境前还必须补齐：

- release/tag selection；
- OCI/image digest；
- transitive SBOM；
- CVE/advisory scan；
- signature/provenance；
- exact build inputs；
- internal mirror receipt；
- compatibility evidence；
- upgrade/rollback evidence。

---

## 2. Registry 字段定义

每个外部依赖必须有：

| 字段 | 含义 |
|---|---|
| Dependency | 平台中的逻辑依赖名 |
| Decision | 来自 WP-P0-01 的主判定 |
| Exact Repo | 本轮核对的上游源码仓库 |
| Audit Revision | 2026-09-25 本轮看到的 exact commit |
| License | 首轮 license 判定 |
| License Evidence | license 文件路径 + Git blob SHA |
| Security / Ops Risk | 已知工程风险；不是漏洞清单 |
| Upstream Health | 本轮是否可继续作为候选；不代表长期承诺 |
| Internal Mirror | 进入部署前的镜像要求 |
| Replacement | Exit Path 的首批替代方向 |
| Owner | 后续负责复核的工作轨道 |
| Review Trigger | 必须重新做依赖 Gate 的条件 |

### License Evidence 说明

本轮使用 **Git blob SHA** 固定被阅读的 license 文件对象。

它的作用是：

- 防止“只写 Apache/MIT 但上游文件后来变了”；
- 为 WP-P0-02 建立 content-addressed evidence；
- 后续生产 pin 时再生成 SHA-256 / SBOM / notice bundle。

因此：

> Git blob SHA 是本轮 License Evidence ID，不等同于最终发行物的 License SHA-256。

---

## 3. Dependency Register

| Dependency | Decision | Exact Repo | Audit Revision | License | License Evidence |
|---|---|---|---|---|---|
| CSGHub | ADAPTER | `OpenCSGs/csghub` | `bbb9bf4b346a199a387090de76fcd6c1fffe98f6` | Apache-2.0 | `LICENSE` · `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` |
| MLflow | ADAPTER | `mlflow/mlflow` | `b641cd61081c9e67d5c0e2cf16a73846b8d6e8ed` | Apache-2.0 | `LICENSE.txt` · `db7cb10b5e330d56b40370bc178974ccabe71458` |
| BentoML | ADAPTER | `bentoml/BentoML` | `517b343b81aeb0b01bbd908e58e53ad9c12ef7eb` | Apache-2.0 | `LICENSE` · `231bcb00f2e3fc427b6e701bc421da36c597a0f9` |
| ModelScope | ADAPTER | `modelscope/modelscope` | `6cb35d56b5e45cf30154d85b56db3c67edb032ac` | Apache-2.0 | `LICENSE` · `d645695673349e3947e8e5ae42332d0ac3164cd7` |
| ms-swift | ADAPTER | `modelscope/ms-swift` | `6c7398def6a48c2a91ead19f8d9ce92fac4ac7d4` | Apache-2.0 | `LICENSE` · `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` |
| SGLang | ADAPTER | `sgl-project/sglang` | `37ebcac3c4be4a7704cff5a0d53bcdf721a8673a` | Apache-2.0 | `LICENSE` · `9c422689c8f5c317c7c65153b1209349ec57007e` |
| vLLM | ADAPTER | `vllm-project/vllm` | `8b365ff949260dbfee92bb319b45333eaff03f6a` | Apache-2.0 | `LICENSE` · `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` |
| llama.cpp | ADAPTER | `ggml-org/llama.cpp` | `f805c57a2d0b7cc171e599303ce2040f6e1bfe15` | MIT | `LICENSE` · `e7dca554bcb802f98408383a864404e3aa4eacca` |
| LiteLLM OSS | ADAPTER | `BerriAI/litellm` | `f61b3c3f38e7eacc6438ba956d8c072dae9132ca` | MIT core; enterprise subtree separate | `LICENSE` · `3bfef5bae9b48c334acf426d5b7f21bc1913aab9` |
| PostgreSQL | REUSE | `postgres/postgres` | `2c10c2ce4d7bcd57543a49ab402af02a39724e0a` | PostgreSQL License | `COPYRIGHT` · `0a397648dcd3c2177acc58bd7daecd11ad64be62` |
| MinIO | RESTRICTED | `minio/minio` | `7aac2a2c5b7c882e68c1ce017d8256be2feea27f` | AGPL-3.0 | `LICENSE` · `be3f7b28e564e7dd05eaf59d64adba1a4065ac0e` |
| NATS Server | REUSE | `nats-io/nats-server` | `eb6f3a8c57867fcfc04e97a1b865a21646c82702` | Apache-2.0 | `LICENSE` · `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` |
| OpenBao | ADAPTER | `openbao/openbao` | `a87e8099310da4c1ca7e812ec97d9700efbc967b` | MPL-2.0 | `LICENSE` · `f4f97ee5853a2b2ba9121ea21589c706edf7a1cc` |
| Harbor | ADAPTER | `goharbor/harbor` | `e5e0e72c7455778dbeda45f4cd0db65a9a371705` | Apache-2.0 | `LICENSE` · `4b9cffeef7f698d791276363a62da9e05023735b` |
| Caddy | REUSE | `caddyserver/caddy` | `7ee4441f9261d649eed215f27331352c1ab5a746` | Apache-2.0 | `LICENSE` · `d645695673349e3947e8e5ae42332d0ac3164cd7` |
| libvirt | ADAPTER | `libvirt/libvirt` | `11d170053ebe9f219d17163c5ddcfb09f3dc1a98` | C API LGPL-2.1+; repository contains GPL-2.0+ portions | `COPYING.LESSER` · `e5ab03e1238af66de157fae2e6270d7e8f967f93` |
| pgvector | REPLACE_LATER baseline | `pgvector/pgvector` | `7db2345ed99bc77bf33cbdc8b12bd1973210dc81` | PostgreSQL License | `LICENSE` · `fc5f177fa5d9c0d20a949f4b4faa028999977008` |
| Qdrant | REPLACE_LATER candidate | `qdrant/qdrant` | `6ab21cac18ebb6f4ae29102c7f8f5cc11affd5de` | Apache-2.0 | `LICENSE` · `456fb05e0e936f439cf42c517b19797dafd53ff9` |
| OpenSearch | REPLACE_LATER candidate | `opensearch-project/OpenSearch` | `f809f8dc0698f2a33cc74da445ec0601284bcb4f` | Apache-2.0 | `LICENSE.txt` · `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` |
| Temporal | BUILD / future execution candidate | `temporalio/temporal` | `d8f9c6d86b2cd0ea5c27d0694a598da84c6d337d` | MIT | `LICENSE` · `3349f76795f4409cba6ae18ea56adf9fbd8346f3` |

---

## 4. Risk / Health / Mirror / Replacement

| Dependency | Security / Operational Risk | Upstream Health for Stage-1 | Internal Mirror Requirement | Replacement / Exit Candidate | Owner |
|---|---|---|---|---|---|
| CSGHub | 中：Hub 权限/资产状态易与平台 Authority 混淆 | Candidate | source + selected image/package + license evidence | ModelScope / HF-compatible source / internal Asset Hub | Track B |
| MLflow | 中高：Run/Registry 状态易被误当平台状态 | Candidate | package/image + migration/export recipe | internal tracker / alternate experiment backend | Track B |
| BentoML | 中：Serving abstraction 与我方 Deployment 可能重叠 | Candidate | package/image + service template | direct OCI serving / runtime adapters | Track B |
| ModelScope | 中：外部 ID、远端可用性、模型自身 license | Candidate | downloaded artifact + manifest + source metadata | other asset sources | Track B/E |
| ms-swift | 中：训练配置/模型兼容变化快 | Candidate | package/image + frozen training env | Transformers/TRL/custom worker | Track E |
| SGLang | 中高：GPU/runtime compatibility、快速迭代 | Candidate | source/package/image + benchmarked build | vLLM / generic serving | Track E |
| vLLM | 中高：GPU/runtime compatibility、快速迭代 | Candidate | source/package/image + benchmarked build | SGLang / generic serving | Track E |
| llama.cpp | 中：format/backend feature drift | Candidate | source/binary + GGUF tooling | other runtimes | Track E |
| LiteLLM OSS | **高**：最接近 northbound gateway；enterprise license boundary | Restricted-to-Adapter | exact OSS source/image; exclude unapproved enterprise code | custom ProviderAdapter / alternate OSS gateway | Track B/D |
| PostgreSQL | 中：核心 state store，恢复和 migration 风险高 | Foundation default | package/image + migration + backup/restore recipe | compatible relational migration if ever justified | Track F/D |
| MinIO | **高**：AGPL-3.0 + 本轮观察到 GitHub repo archived；不得形成长期锁定 | **Restricted** | only after legal/ops gate; never sole copy during evaluation | Ceph RGW / Garage / cloud S3 / other S3-compatible | Track F |
| NATS | 中：错误地把 stream 当 canonical state 会造成 Authority 漂移 | Foundation default | image/package + stream config | alternative broker via MessagingAdapter | Track F/D |
| OpenBao | 高：secret / identity / policy boundary | Candidate | package/image + bootstrap/restore docs | alternate SecretAdapter backend | Track F |
| Harbor | 中：registry metadata/tag 与平台 artifact lifecycle 重叠 | Candidate | image/chart + database/registry backup recipe | other OCI Distribution-compatible registry | Track F |
| Caddy | 低中：Edge config / TLS operational dependency | Candidate default | binary/image + config generator | Nginx/HAProxy/Envoy if evidence requires | Track F |
| libvirt | 中：host privilege、hypervisor behavior、mixed license areas | Foundation KVM candidate | OS package/repo pin + host compatibility matrix | VMware / Proxmox / Incus adapters | Track F |
| pgvector | 中：DB load coupling；规模上升可能失配 | Stage-1 baseline | PostgreSQL extension package + rebuild recipe | Qdrant / another VectorAdapter | Track B/F |
| Qdrant | 中：额外 stateful service；不应过早引入 | Deferred candidate | image + snapshot/restore + rebuild proof | pgvector / other vector backend | Track B/F |
| OpenSearch | 中高：额外 JVM/stateful cluster 运维成本 | Deferred candidate | image + config + full rebuild proof | PostgreSQL FTS / other SearchAdapter | Track B/F |
| Temporal | **高架构风险**：若直接建模 workflow 会制造第二 Authority | **Deferred; do not introduce Stage-1** | none until P7 evidence gate | Go Control Hub workflow semantics remain Authority | Track D |

### 4.1 MinIO 特别处理

Stage-1 的冻结对象是：

```text
S3-compatible Object Storage
```

不是：

```text
MinIO-specific Platform Contract
```

因此在 P4 Object Storage 选型前必须比较至少：

- operational fit；
- license obligations；
- upstream status；
- migration/export；
- checksum/versioning；
- multipart；
- retention；
- backup/restore；
- local deployment footprint。

在该 Gate 前，MinIO 不得被写入 Domain/API 作为品牌型依赖。

### 4.2 LiteLLM 特别处理

允许进入 bakeoff 的范围仅是：

- OSS core；
- Provider protocol normalization；
- compatible routing/provider adapter behavior。

以下不能直接成为平台 Authority：

- LiteLLM user/team/project semantics；
- virtual key 作为平台 identity；
- internal routing policy；
- enterprise-only feature 作为 Frozen Contract 前提。

如确需 enterprise subtree，必须单独创建 License/Commercial Gate。

### 4.3 Temporal 特别处理

Temporal 的 License 没有阻止采用，但架构边界阻止 Stage-1 直接引入第二 Workflow Authority。

未来只有当 Evidence 证明：

- Go Control Hub + PostgreSQL + NATS 的 durable workflow 能力不足；
- failure/replay/long-running semantics 成为明确瓶颈；

才允许评估 Temporal，并且仍须满足：

```text
Our Workflow
Our Approval
Our Gate
Our Evidence
        ↓
WorkflowAdapter
        ↓
Temporal execution
```

---

## 5. Mirror Policy

第三方真正进入可执行环境之前，必须建立内部可重建证据链：

```text
Upstream Repo / Release
        ↓
Exact Revision / Tag
        ↓
License Evidence
        ↓
Source Archive / Package / Image Digest
        ↓
SBOM
        ↓
Security Scan
        ↓
Compatibility Test
        ↓
Internal Mirror
        ↓
Approved Deployment Pin
```

### 5.1 必须镜像

以下类型进入 Stage-1 后必须可从内部镜像恢复：

- runtime source/package/image；
- database/broker/secret/registry/edge images；
- Python wheels / Go modules 中的 critical direct dependency；
- CUDA/runtime-specific binaries；
- selected model/dataset manifests；
- license and notice bundle。

### 5.2 不允许

- 生产启动时永远依赖公网 `latest`；
- 只保存 tag 不保存 digest；
- 镜像了 container 但没有 license/SBOM；
- 只保存二进制，不保存可定位 upstream revision；
- upstream 删除后无法重建环境。

---

## 6. Security Gate 输入

本 WP **没有**声称“这些依赖当前没有 CVE”。

进入 P4/P5 的 exact Deployment Pin 时必须重新执行：

1. source/release advisory check；
2. transitive dependency SBOM；
3. container/base image scan；
4. signature/provenance check；
5. known exploitability review；
6. network exposure review；
7. secret handling review；
8. privilege requirement review；
9. EOL/deprecation review；
10. restore/rollback test。

结果进入 `Evidence`，而不是只写在 README。

---

## 7. Review Trigger

任何依赖出现以下事件时必须重新审查：

- License 文件/blob 变化；
- license model 变化；
- repository archived / transferred / abandoned；
- upstream security incident；
- major version upgrade；
- incompatible API change；
- EOL；
- critical CVE；
- new privilege requirement；
- data export/telemetry behavior change；
- closed-source/enterprise dependency进入关键路径；
- observed performance/reliability regression；
- replacement candidate 显著更优。

---

## 8. P1 / P4 / P5 handoff

### 给 P1

- Domain 不保存第三方 DTO；
- `UpstreamDependency` 必须能引用 exact repo/revision/license evidence；
- `Adapter` 必须有 backend/version/capability/evidence；
- `Artifact` 必须有 digest/provenance/source；
- `Index` 是可重建派生物；
- Provider / Serving / Workflow / Virtualization / Secret / Object Storage 等边界继续由 P1 Contract 固化。

### 给 P4

真正部署基础设施时，必须从本表生成：

```text
Candidate
→ selected release
→ exact deployment pin
→ image/package digest
→ SBOM
→ mirror receipt
→ restore evidence
```

### 给 P5

每个 External Backend Integration 必须通过：

- Adapter conformance test；
- import/export test；
- backend unavailable test；
- replacement smoke；
- no-third-party-DTO northbound test；
- evidence capture。

---

## 9. Acceptance Criteria

- [x] 已覆盖 WP-P0-01 的主要第三方实现与 deferred candidates；
- [x] 每个候选有 exact repo；
- [x] 每个候选有本轮 audit revision；
- [x] 每个候选有 License 首判；
- [x] License 文件以 Git blob SHA 固定；
- [x] 已记录 security/operational risk；
- [x] 已记录 internal mirror 要求；
- [x] 已记录 replacement candidate；
- [x] 明确 Audit Revision ≠ Production Deployment Pin；
- [x] 明确 SBOM/CVE/image digest 在实际选版时重新生成；
- [x] MinIO / LiteLLM / Temporal 的特殊风险已单独处理；
- [x] 不改变 Frozen Architecture。

---

## 10. Exit Condition

WP-P0-02 在设计阶段的 Exit Condition：

> P1/P4/P5 已经可以仅根据本文件与 WP-P0-01，知道每一个关键外部依赖的“来源、证据、风险、边界、镜像要求、替代路径和再次审查条件”。

真正生产依赖锁定由后续 P4/P5 完成，不在本 WP 提前伪造。

# Technology Stack Baseline v1.0

> 状态：**技术栈已冻结（Technology Stack Frozen v1.0）**
>
> 上位 Authority：`docs/design/00-FUNCTIONAL-ARCHITECTURE.md`
>
> 原则：技术栈必须服务于“松耦合、可替换、可迁移、可自主化”。框架是实现，不是 Authority。

---

# 1. 总体结论

平台采用三层主技术栈：

```text
Frontend
React + TypeScript

Control Plane
Go

AI / ML Execution Plane
Python
```

核心理由：

- 前端需要大型控制台、复杂状态、数据可视化和长期自有 UI；
- Control Hub / Scheduler / Gateway / Adapter Manager 需要高并发、长时间稳定运行、低资源占用和清晰并发模型；
- AI/ML 训练、推理、数据处理和科研生态仍以 Python 为主；
- 三层通过稳定 Contract 解耦，不要求使用同一种语言。

---

# 2. Frontend Stack

## 2.1 基线

```text
React 19.x
TypeScript 7.x
Vite 8.x
React Router 8
TanStack Query
shadcn/ui
Base UI
Tailwind CSS
```

Node.js 构建环境：

```text
Node.js 24 LTS
```

实施时锁 exact minor / patch，不使用 `latest` 漂移。

## 2.2 为什么不选 Next.js 作为默认

本项目首先是：

- 内部 Control Hub；
- 自托管；
- API-first；
- SPA-heavy；
- 实时状态与复杂工作台；
- 不依赖 SEO；
- 不要求服务端渲染。

因此默认采用：

```text
Vite SPA
+ Independent Control Hub API
```

避免将 UI 与 Node Server / SSR / React Server Component 生命周期绑定。

如果未来出现真正需要 SSR / Public Portal 的独立站点，再单独增加 Web Adapter / Public Frontend，不改变 Control Hub。

## 2.3 Routing

采用 React Router 8。

默认使用：

```text
Data Mode
```

原因：

- 保留前端构建与 API 层控制权；
- 支持 loader / action / pending；
- 不强绑定 Framework Mode 的服务端架构；
- 后续如有必要仍可升级 Framework Mode。

## 2.4 Server State

采用 TanStack Query：

- Query；
- Mutation；
- Cache；
- Invalidation；
- Background Refresh；
- Retry；
- Polling。

原则：

> Server State 不复制进大型全局前端 Store。

客户端本地 UI 状态优先：

- URL State；
- React Local State；
- Context。

只有出现明确跨工作台复杂共享状态时，再引入 Zustand 等轻量 Store。

默认不采用 Redux。

## 2.5 UI Component Strategy

采用：

```text
shadcn/ui
+ Base UI
+ 自有 Design Tokens
```

原因：

- Open Code；
- 组件代码归自己；
- 可以深度修改；
- 不被第三方主题系统锁死；
- 适合我们的自有 UI / Design System。

正式 UI 不继承 CSGHub / MLflow / LiteLLM 的 IA 和视觉结构。

第三方 Portal 只作为：

- Admin fallback；
- Debug UI；
- Feature Reference。

## 2.6 Visual / Data Components

候选：

- Apache ECharts：Dashboard / GPU / Cost / Benchmark；
- React Flow：Workflow / DAG / Lineage；
- Cytoscape.js：大型 Graph / Topology（需要时）；
- Monaco Editor：JSON / YAML / Policy / Config 编辑（需要时）。

这些均属于可替换 UI Capability，不进入 Domain Model。

## 2.7 Forms / Validation

建议：

```text
React Hook Form
+ Zod
```

但 API 类型优先由 OpenAPI / JSON Schema 自动生成，禁止手工重复维护前后端 DTO。

## 2.8 Frontend Testing

```text
Vitest
Testing Library
Playwright
```

必须覆盖：

- Domain Contract；
- Golden Journey；
- Human Approval；
- Permission；
- Critical UI State；
- Regression。

---

# 3. Control Plane Backend

## 3.1 主语言

```text
Go 1.26.x
```

承担：

- Control Hub API；
- Capability Registry；
- Policy；
- Gate；
- Scheduler Controller；
- Resource Manager；
- Adapter Manager；
- Provider Routing Control；
- Deployment Controller；
- Upstream Risk Registry；
- License Gate；
- Human Approval；
- Audit / Lineage Coordination；
- Event Coordination。

## 3.2 为什么核心后端不用纯 Python

Python 非常适合 AI Worker，但不建议成为整个 Control Plane 的唯一语言。

Control Plane 需要：

- 长期常驻；
- 大量并发 I/O；
- Lease / Watchdog；
- Controller Loop；
- Scheduler；
- Gateway；
- 高可预测性；
- 低内存；
- 单 Binary 部署。

Go 更适合承担稳定控制面。

Python 继续承担其优势领域：

- Torch；
- Transformers；
- Training；
- Data Science；
- Evaluation；
- Model-specific Integration。

## 3.3 HTTP Framework

默认：

```text
Go net/http
+ chi
```

保持轻量。

不把 Gin / Echo / Fiber 等框架语义暴露到 Domain 层。

第三方项目即便使用 Gin，也只通过 Adapter/API 对接。

## 3.4 API-first

北向 Control Hub API：

```text
REST / JSON
OpenAPI 3.1
```

OpenAPI 是客户端 Contract Authority。

自动生成：

- TypeScript Client；
- Go Client；
- Python Client；
- Mock / Contract Tests。

高频内部路径如未来确有必要，可增加：

```text
gRPC / Protobuf
```

但不作为 Stage-1 默认。

## 3.5 Real-time UI

默认优先：

```text
SSE
```

用于：

- Job Progress；
- GPU State；
- Deployment State；
- Approval；
- Event Timeline。

只有真正需要双向实时交互的场景才使用 WebSocket。

---

# 4. AI / ML Execution Plane

## 4.1 Python Baseline

```text
Python 3.12
uv
Pydantic 2
pytest
```

Python 3.12 作为第一阶段兼容基线，避免追逐最新解释器导致 CUDA / Torch / Training Framework 兼容风险。

Python Environment 必须按 Worker / Runtime Profile 隔离，不要求全平台只有一个 Python 环境。

## 4.2 Python 负责

- Model Intake；
- Inference Adapter；
- Training；
- Fine-tuning；
- Quantization；
- Embedding；
- Reranker；
- Industrial AI；
- Data Factory；
- Evaluation；
- Research Reproduction；
- BentoML Worker；
- ms-swift Worker；
- MLflow Integration；
- Model-specific Tooling。

## 4.3 Python Worker API

需要网络服务时默认：

```text
FastAPI
+ Pydantic
```

但 FastAPI 只是 Worker API Framework，不承担平台 Core Authority。

---

# 5. Data & State

## 5.1 Metadata / Transactional SoT

```text
PostgreSQL 18
```

用于：

- Domain Metadata；
- Registry；
- Policy；
- Gate；
- Approval；
- Allocation / Lease Metadata；
- Lineage Metadata；
- Upstream Risk；
- Audit Index。

禁止让 Redis / Queue / MLflow / CSGHub 数据库成为平台唯一 Authority。

## 5.2 SQL Access

Go 侧建议：

```text
pgx
+ sqlc
```

优先明确 SQL 和编译期类型，不采用重 ORM 作为 Domain Authority。

## 5.3 Artifact / Object Storage

统一：

```text
S3-compatible Object Storage
```

第一阶段可使用 MinIO / 现有 S3-compatible 服务。

存放：

- Model；
- Dataset；
- Checkpoint；
- Evidence；
- Benchmark；
- Export；
- Backup；
- Repro Package。

必须 content-addressable / hash-aware。

---

# 6. Event / Messaging / Workflow

## 6.1 Event & Messaging Baseline

第一阶段：

```text
NATS + JetStream
```

用于：

- Event Bus；
- Job Dispatch；
- Consumer；
- Replay；
- Retry；
- Dead Letter；
- Backpressure。

Kafka / Redis Streams / RabbitMQ 保留 Adapter。

## 6.2 Durable Workflow

不在 Stage-1 自己重写完整 Workflow Engine。

先定义：

```text
Workflow Contract
State Machine
Idempotency
Retry
Compensation
Human Gate
Event Wait
```

然后通过 Adapter 接成熟 Workflow Backend。

后续如达到战略自主化条件，再 Native Replace。

---

# 7. Identity & Security

平台只定义：

```text
OIDC / OAuth2
RBAC / ABAC Semantics
Service Account
Workload Identity
```

实际 Identity Provider 可替换。

第一阶段可以接：

- Keycloak；
- 组织现有 OIDC；
- 其他兼容 Provider。

前端和服务不得绑定某一家 IdP 专有对象。

Secret 通过 Secret Broker / Reference 管理，禁止存入代码库和普通数据库明文字段。

---

# 8. Observability

统一采用：

```text
OpenTelemetry
```

输出：

- Trace；
- Metric；
- Log correlation；
- Request ID；
- Job / Experiment correlation。

Backend 可替换：

- Prometheus；
- Grafana；
- Loki；
- Tempo；
- 其他 OTel-compatible backend。

Observability backend 不是 Authority。

---

# 9. External Reuse Layer

建议定位：

```text
CSGHub
→ Asset Hub Backend

MLflow
→ Experiment / Evidence Backend

BentoML
→ Generic AI/ML Serving

SGLang / vLLM / llama.cpp
→ LLM/VLM Runtime

ModelScope / ms-swift
→ Model Source / Training Adapter

LiteLLM OSS / Alternatives
→ Optional Gateway / Provider Adapter
```

所有第三方均处于 Adapter 后面。

---

# 10. Virtualization & Host Layer

虚拟化必须作为正式一级基础设施层，而不是隐藏在 Deployment 细节里。

## 10.1 默认虚拟化技术

第一阶段默认：

```text
KVM
+ QEMU
+ libvirt
```

原因：

- Linux 原生；
- 成熟稳定；
- 无强制商业控制面；
- API / CLI 完整；
- 适合 Headless Server；
- 支持 PCIe / GPU Passthrough；
- 可以通过 Adapter 与其他虚拟化平台并存。

平台不直接绑定 libvirt 对象，而定义：

```text
VirtualizationAdapter
├── LibvirtAdapter
├── VMware / vSphere Adapter
├── Incus Adapter
├── Proxmox Adapter
└── Future Hypervisor Adapter
```

## 10.2 完整运行层级

平台允许：

```text
Physical Hardware
        ↓
Virtualization
        ↓
Guest OS
        ↓
OCI Container
        ↓
AI Runtime / Worker
        ↓
Model / Capability
```

但这不是强制每个工作负载都经过所有层。

允许两条主要路径：

### Bare-metal Path

```text
Host Linux
→ Container
→ Runtime
→ Model
```

适合：

- 已验证生产推理；
- 极致性能；
- 稳定 Driver / CUDA；
- 可信内部 Workload。

### VM-isolated Path

```text
Host Linux
→ VM
→ Guest Linux
→ Container
→ Runtime
→ Workload
```

适合：

- 未知第三方代码；
- 不同 Kernel / Driver 要求；
- CUDA / Driver 冲突；
- 高风险模型或工具；
- 强隔离实验；
- Reproduction；
- Quarantine。

## 10.3 GPU Virtualization Policy

对于 RTX 4090 等消费级 GPU，默认按：

```text
Whole-GPU PCI Passthrough
VFIO / IOMMU
```

处理 VM GPU 隔离。

不得把 MIG / vGPU 视为通用可用能力。

GPU 分配进入 Resource Contract：

```text
GPU
→ Host Ownership
→ Drain
→ Detach
→ VM Assignment
→ Guest Probe
→ Workload
→ Release
→ Host Reattach / Next Assignment
```

整个过程必须有：

- Lease；
- Fencing；
- Health Check；
- Rollback；
- Evidence。

## 10.4 VM Image / Provisioning

VM 作为版本化 Environment Asset 管理。

建议：

```text
Cloud Image
+ cloud-init
+ Immutable Base Image
+ Runtime Overlay
```

每个 VM Image 至少记录：

- OS；
- Kernel；
- Image Hash；
- Source；
- Build Revision；
- Driver Compatibility；
- CUDA Compatibility；
- Security Patch Level；
- Created At；
- Parent Image；
- Environment Profile。

不依赖人工“点出来”的不可复现 VM。

## 10.5 Guest Integration

优先：

- cloud-init；
- QEMU Guest Agent；
- SSH / Workload Agent；
- Metadata / GuestInfo Adapter（特定平台需要时）。

平台通过自己的 VM Contract 管理：

```text
Create
Start
Stop
Snapshot
Clone
Attach GPU
Detach GPU
Inspect
Health
Destroy
```

而不是把业务逻辑绑定到某个 Hypervisor API。

## 10.6 VM Classes

延续功能架构的隔离分类：

```text
STABLE
CANDIDATE
EXPERIMENTAL
QUARANTINE
```

其中 Quarantine VM 默认：

- Restricted Egress；
- No Production Secret；
- Separate Storage Namespace；
- Restricted Tool Scope；
- Full Audit。

## 10.7 VM 与 Container 的职责边界

默认判断：

```text
Kernel / Driver / Trust Boundary 不同
→ VM

Python / CUDA userspace / Framework 不同
→ Container

Model / LoRA / Quantization 不同
→ Deployment Artifact

Hyperparameter 不同
→ Experiment
```

避免为了每个模型创建 VM，也避免把需要强隔离的未知代码硬塞进共享 Container。

## 10.8 VM Control Plane

Go Control Plane 增加：

```text
VM Inventory
Image Registry
Placement
Lifecycle
GPU Passthrough Coordination
Guest Health
Snapshot / Restore Metadata
Isolation Policy
```

实际执行通过 Virtualization Adapter 完成。

---

# 11. Deployment Baseline

Stage-1 不引入 Kubernetes 作为前提。

采用：

```text
Physical / VM Host
        ↓
OCI Container
        ↓
Docker Compose / Dev & Bootstrap
containerd + NVIDIA CDI / Production Candidate
systemd / Supervisor for Core Control Services where appropriate
```

未来多节点再通过 Adapter 接：

- Kubernetes；
- Kueue；
- Slurm；
- Ray；
- 其他 Scheduler Backend。

---

# 12. Repository Structure Candidate

建议在当前阶段保持一个主要工程仓，避免过早拆成大量 repo：

```text
apps/
  web/

services/
  control-hub/
  gateway/

workers/
  model-intake/
  training/
  evaluation/
  data/
  research/

adapters/
  csghub/
  mlflow/
  bentoml/
  providers/
  vector/
  search/
  messaging/

contracts/
  openapi/
  events/
  schemas/

deploy/
  compose/
  systemd/
  containerd/

docs/
  design/
```

第三方完整源码默认不 vendoring 到主仓；通过固定版本、镜像、submodule/patch policy 或独立 mirror 管理。

---

# 13. Version Policy

冻结的是技术族和 Contract，不永久冻结 minor 版本。

规则：

```text
Stable Release
→ Pin exact version
→ CI
→ Contract Test
→ Security Scan
→ Candidate Upgrade
→ Promote
```

禁止：

```text
latest
unbounded dependency
automatic major upgrade
```

---

# 14. 明确不选

第一阶段默认不采用：

- Next.js 作为 Control Hub Shell；
- Node.js 作为核心 Control Plane；
- Python 单语言承载整个 Control Plane；
- Kubernetes-first；
- Microservice-per-feature；
- Heavy ORM；
- Redux-first；
- GraphQL-first；
- WebSocket-everywhere；
- 第三方 UI 作为正式 Product Shell。

---

# 15. 技术栈一句话

> **React/TypeScript 做自有 UI，Go 做稳定可替换的 Control Plane，Python 承载 AI/ML 生态；KVM/QEMU/libvirt 提供默认 VM 隔离层，OCI/containerd 提供容器层，PostgreSQL 保存平台主状态，S3 保存资产，NATS 负责事件与异步，OpenAPI/JSON Schema 负责 Contract，所有第三方实现都留在 Adapter 后面。**

这套技术栈与 Functional Architecture 的“Universal Replaceability Principle”一致。

---

# 16. Network / Edge / Service Discovery

## 16.1 North-South Edge

Stage-1 默认：

```text
Caddy
→ TLS termination
→ Reverse Proxy
→ Static Web
→ Control Hub / Gateway
```

Caddy 当前主仓为 Apache-2.0，可作为默认 Edge 实现，但必须位于 `EdgeAdapter` / Deployment 层，不进入 Domain Model。

未来可替换：

- Nginx；
- Envoy；
- Traefik；
- Hardware / Existing Enterprise LB。

## 16.2 East-West

Stage-1 不引入 Service Mesh。

采用：

```text
Private Network
+ Host Firewall
+ Explicit Service Identity
+ Control Hub Registry
+ DNS
```

主机网络策略优先使用 Linux 原生 `nftables` / Network Policy Adapter。

只有在多节点规模、mTLS、流量治理复杂度达到真实门槛后，再评估 Service Mesh。

## 16.3 Service Discovery

Stage-1 不引入 Consul。

服务实例通过：

```text
Control Hub Registry
+ Health / Lease
+ Explicit Endpoint
+ DNS where appropriate
```

完成发现。

---

# 17. Configuration / Secret / Feature Flags

## 17.1 Configuration

非 Secret 配置：

```text
Versioned YAML / TOML / JSON
+ JSON Schema
+ Environment-specific Overlay
```

规则：

- 配置可审计；
- 配置可 diff；
- 配置可 rollback；
- Production 配置必须固定 Revision；
- 禁止不可追踪的人工配置漂移。

## 17.2 Secret Management

Bootstrap 阶段允许：

```text
runtime-injected secret
+ protected file
+ environment reference
```

长期默认 Secret Broker 候选：

```text
OpenBao
```

OpenBao 当前主仓为 MPL-2.0。

平台只保存：

```text
Secret Reference
Secret Scope
Rotation Metadata
Access Policy
```

不保存生产 Secret 明文。

Secret Backend 保持可替换。

## 17.3 Feature Flags

平台定义：

```text
Feature Flag Contract
```

优先兼容 OpenFeature 语义，但 Stage-1 不强制部署独立 Feature Flag Server。

小规模功能开关可以由 Control Hub Policy / Config 管理；规模扩大后再接专用 Backend。

---

# 18. OCI / Package / Supply-chain Distribution

## 18.1 OCI Registry

Bootstrap 可以使用标准 OCI Distribution。

生产候选：

```text
Harbor
```

Harbor 当前主仓为 Apache-2.0，适合承担：

- OCI Image Registry；
- Artifact Distribution；
- RBAC；
- Replication；
- Vulnerability Scan Integration；
- Retention。

Harbor 仍然只是 Artifact Backend，不是平台 Registry Authority。

## 18.2 Artifact Pinning

生产必须使用：

```text
image@sha256:<digest>
```

而不是仅依赖 mutable tag。

每个发布单元至少记录：

- Image Digest；
- SBOM；
- Source Revision；
- Build Provenance；
- License Inventory；
- Signature / Attestation（可用时）。

## 18.3 Package Mirror

Python / Node / Go 依赖必须可被内部缓存或镜像。

但 Stage-1 不冻结某一个统一 Package Repository 产品。

后续通过：

```text
PackageMirrorAdapter
```

接入 Python Index / npm Proxy / Go Proxy / OS Package Mirror。

---

# 19. Database Migration

PostgreSQL Schema Migration 默认采用：

```text
golang-migrate / migrate v4
```

当前主仓 MIT。

Migration 规则：

- migration file 入 Git；
- migration 与应用 Revision 对齐；
- CI 检查 forward migration；
- destructive migration 单独 Gate；
- 大表变更需 online / staged migration；
- Production migration 必须有 backup / rollback plan。

Domain Schema 不由 ORM 自动漂移。

---

# 20. Infrastructure as Code / Provisioning

基础设施必须可重建。

默认：

```text
OpenTofu
+ cloud-init
+ shell / targeted configuration scripts
```

OpenTofu 当前主仓 MPL-2.0。

负责：

- VM；
- Network；
- Storage；
- Base Infrastructure；
- Infrastructure Inventory linkage。

配置管理工具如 Ansible 可以作为可选 Adapter 使用，但不是平台运行时 Authority。

原则：

> **Infrastructure change is reviewed code, not an undocumented console click.**

对于已有 VMware / vSphere、libvirt 等环境，通过各自 Provider / Adapter 对接，不把核心 Contract 绑定到单一 Provider。

---

# 21. CI / CD / Release Engineering

第一阶段采用：

```text
GitHub Actions
+ self-hosted runner where hardware/GPU access is required
```

CI 负责：

- Lint；
- Unit Test；
- Contract Test；
- License / SBOM；
- Security Scan；
- Build；
- Integration Test；
- UI E2E；
- Reproducibility checks。

GPU / Hardware Test 优先放自托管 Runner，避免公共 CI 成为 GPU Authority。

CD 不允许：

```text
merge → uncontrolled production
```

而是：

```text
Build
→ Signed / Hashed Artifact
→ Candidate
→ Integration / Shadow / Canary
→ Gate
→ Human Approval where required
→ Promote
```

Production deployment 由 Control Hub / Release Contract 执行，不让 CI 平台成为第二 Authority。

---

# 22. Backup / Recovery Implementation Baseline

功能架构已有 Backup / DR Contract；技术实现补充为：

## PostgreSQL

至少支持：

```text
Base Backup
+ WAL Archiving / PITR
+ Off-host Copy
+ Periodic Restore Test
```

具体 Backup Backend 可替换。

## Object Storage

要求：

- Versioning where appropriate；
- Replication / Backup Policy；
- Immutable Evidence retention where required；
- Content Hash Verification。

## Config / Registry / IaC

Git 本身不是唯一 Backup。

关键配置、Contract、IaC、Registry Export 进入独立备份策略。

## Recovery

必须定期验证：

```text
Fresh Host / VM
→ Restore Metadata
→ Restore / Reconnect Artifact
→ Recreate Environment
→ Re-register Runtime
→ Recover Service
```

没有 Restore Test 的 Backup 不计为 DR Evidence。

---

# 23. Cache Policy

Stage-1 **不默认引入 Redis**。

默认：

```text
bounded in-process cache
+ PostgreSQL
+ NATS JetStream where durable event state is needed
```

只有出现以下真实需求再引入分布式 Cache：

- 多实例共享热点状态；
- 明确延迟瓶颈；
- 高并发 Rate Limit；
- Short-lived distributed coordination。

即使引入 Redis / Valkey，也必须作为 `CacheAdapter`，不得成为唯一 Authority。

---

# 24. Technology Stack Freeze v1.0

经过最终缺口审计，本技术栈基线完成收敛。

完整层级：

```text
Our React / TypeScript UI
          ↓
Caddy / Edge
          ↓
Go Control Hub / Gateway / Scheduler
          ↓
Capability & Adapter Contracts
          ↓
Python AI/ML Workers + Reused Backends
          ↓
OCI / containerd
          ↓
Guest Linux when isolation is required
          ↓
KVM / QEMU / libvirt or Virtualization Adapter
          ↓
Physical GPU / CPU / RAM / NVMe / Network

State:
PostgreSQL

Assets:
S3-compatible Object Storage

Events:
NATS + JetStream

Secrets:
Secret Broker / OpenBao candidate

Images:
OCI Registry / Harbor candidate

IaC:
OpenTofu + cloud-init

Observability:
OpenTelemetry

CI:
GitHub Actions + self-hosted hardware runners
```

## 24.1 Stage-1 明确不额外引入

没有真实需求前，不增加：

- Kubernetes；
- Service Mesh；
- Consul；
- Redis / distributed cache；
- Dedicated Feature Flag Server；
- GraphQL Gateway；
- Multiple competing workflow systems；
- Microservice-per-feature。

## 24.2 允许修改本技术栈基线的条件

后续普通依赖升级不修改本文件。

只有以下情况触发技术栈 Architecture Change：

- 当前技术族无法满足 Frozen Functional Architecture；
- License / Security 风险发生重大变化；
- 实测证明存在不可接受的性能或可靠性瓶颈；
- 新硬件 / 虚拟化 / Runtime 无法通过现有 Adapter 接入；
- 关键依赖达到 EOL；
- 有明确 Evidence 证明替换收益显著。

至此，技术栈从 **Freeze Candidate** 转为 **Frozen v1.0**。


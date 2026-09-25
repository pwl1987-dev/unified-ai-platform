# AI Compute & Model Engineering Platform 总体功能设计 v1.0

> 状态：**功能架构冻结候选（Functional Architecture Freeze Candidate）**  
> 当前承载仓库：`qwen3.8-27b-8x4090-stack`；**平台设计本身不绑定该仓库名称、Qwen 模型族或 8×RTX4090 单一硬件形态。**  
> 当前角色：本仓现有 Qwen3.8-27B × 8×RTX4090 优化工程仅作为 **Reference Workload #001 / Bootstrap Implementation**，用于以真实实验资产验证平台 Contract。  
> 本文只冻结总体功能边界、核心对象、生命周期、调度原则与自动化闭环；**UI / UX / Human-AI Interaction 另行设计，不在本文展开。**


---

# 阅读导航：先用 10 分钟理解这套平台

这份文档同时面向 **人和机器**。

- 对人：它是一份“这套平台为什么做、能做什么、怎么运转、边界在哪里”的总纲；
- 对研发：它是后续模块拆分、接口设计、状态机和数据模型的上位输入；
- 对 Agent：它提供不可随意越过的 Authority、Gate、生命周期和调度原则；
- 对管理者：它说明这套平台如何把算力、模型、数据、研究、应用和成果转化串成闭环。

如果只想快速理解项目，不必从头逐条读完全部 Contract。先读本节，再按角色进入对应章节。

## A. 一句话定义

> 这不是单纯的“8×4090 GPU 管理后台”，也不是某一个 Qwen 模型的部署工具。  
> 它要建设成一个 **AI 算力、模型工程、数据工程、自动实验、统一服务和持续创新的一体化平台**。

平台希望把过去需要人工分别完成的事情：

```text
找模型
找论文
找数据
搭环境
装驱动
选 GPU
跑推理
做训练
做量化
做 Benchmark
清洗标注
调副本
处理高峰
复现实验
整理报告
申请成果
```

逐步收敛成：

```text
Goal
+ Policy
+ Budget
+ Security Boundary
+ Acceptance Criteria
        ↓
平台自动规划、执行、验证、调度、恢复和迭代
        ↓
关键节点由人审批
```

## B. 为什么要做

当前 AI 工程通常被拆散在很多工具和人工流程里：

- GPU 有自己的管理方式；
- 模型有各自启动脚本和端口；
- SGLang、vLLM、训练框架各自维护环境；
- 外部 Provider 又是另一套 API；
- 数据采集、清洗、标注、训练、评测互相割裂；
- 新论文、新模型、新算法需要人工找、人工复现；
- 实验数据做完以后容易散落；
- 真正上线时还要重新解决容量、弹性、SLA、回滚；
- 有价值的创新成果往往到最后才想起整理论文、专利或软著。

本平台要解决的核心问题是：

> **把这些割裂的环节放进同一套 Authority、Registry、Scheduler、Gate 和 Lineage 中，形成能够持续自动运行的闭环。**

## C. 最终用户看到的，不应该是“GPU 和端口”

应用系统理想状态下只调用：

```text
https://<gateway>/v1
```

例如请求：

```text
model = coding
model = vision
model = meeting-assistant
model = auto
```

调用方不需要知道：

- 模型实际运行在哪张 GPU；
- 当前有几个副本；
- 是 SGLang 还是 vLLM；
- 是哪一个本地模型族、哪一个本地 Runtime，还是外部 Provider；
- 是否临时扩容；
- 是否由 ASR + VLM + OCR + LLM 组合完成；
- 内部使用了哪个端口。

平台内部自动完成能力选择、资源放置、扩缩容、故障恢复和路由。

## D. 平台真正管理的六类东西

从人的视角，不需要先记住所有 Registry 名称。可以先理解成六类资产和工作：

| 类别 | 人能理解的含义 | 典型内容 |
|---|---|---|
| **算力** | 有哪些机器和 GPU，状态如何 | GPU、CPU、RAM、NVMe、网络、功耗、温度 |
| **环境** | 模型在什么软件环境里运行 | Driver、CUDA、PyTorch、VM、Container、Runtime |
| **模型能力** | 平台能提供什么 AI 能力 | LLM、VLM、ASR、TTS、OCR、Embedding、图像、视频 |
| **数据知识** | 模型从哪里学习、依据什么回答 | Dataset、知识库、Ontology、标注、Gold Set |
| **实验与服务** | 如何验证、优化并上线 | 训练、量化、Benchmark、部署、弹性、副本 |
| **研究与成果** | 如何吸收外部技术并形成自己的成果 | 论文复现、技术雷达、报告、专利、软著 |

## E. 三个最典型的使用场景

### 场景 1：把本地 GPU 变成统一 AI 服务

```text
接入模型
→ 自动检查环境
→ Benchmark
→ Gate
→ 部署
→ 注册逻辑模型
→ /v1 统一 API
→ 自动扩缩副本
→ 高峰优先保障业务
```

### 场景 2：从零建设一个领域 AI

例如“沂蒙精神领域 AI”：

```text
定义领域目标
→ 自动发现/导入资料
→ OCR / ASR / 文档解析
→ 清洗 / 去重 / 标注
→ 知识工程
→ 构造训练集与 Gold Set
→ 判断 RAG / SFT / LoRA / CPT
→ 自动训练与评测
→ Gate
→ 上线 API
→ 持续更新
```

### 场景 3：验证最新论文并转化成自己的技术

```text
发现论文/项目
→ Agent 初筛
→ 生成复现 Contract
→ 隔离环境重跑
→ 与当前 Baseline 对比
→ Ablation
→ 形成 Evidence
→ 有价值则接入平台
→ 继续优化
→ 形成技术报告/论文/专利/软著候选
```

## F. 平台的自动化边界

这套系统追求高自动化，但不是“让 Agent 随意控制一切”。

### 系统可以自动做

- 发现技术；
- 拆解实验；
- 采集允许的数据；
- 清洗和标注；
- 调度 GPU；
- 启停模型；
- 扩缩副本；
- 训练、量化和 Benchmark；
- Checkpoint / Resume；
- 故障恢复；
- Shadow / Canary；
- 生成报告和成果材料候选；
- 根据反馈提出下一轮优化。

### 系统不能自行越权

- 降低冻结 Gate；
- 修改核心 Authority；
- 擅自把敏感数据发往外部 Provider；
- 无限消耗 GPU、电力或外部 API 预算；
- 删除失败 Evidence；
- 把 Benchmark 数据混入训练集；
- 未经授权正式发布生产版本；
- 未经授权完成不可逆法律申报。

核心原则：

> **Agents drive the workflow; the platform controls authority.**

## G. 资源调度用一句话理解

平台不是“生产业务独占所有 GPU”，也不是“训练任务永远靠边站”。

目标是：

> **业务 SLA 第一，空闲资源尽量吃满，训练测试不被永久饿死。**

典型状态：

```text
白天高峰：
业务优先占用更多 GPU
训练自动 checkpoint / 缩容 / 暂停

业务低谷：
空闲 GPU 自动回流到训练、Benchmark、数据处理、AutoLab

深夜：
如果业务很少，大部分甚至全部可用 GPU 自动进入 Batch Pool
```

同时通过 Fair Share、Aging、Training Debt、Backfill 等机制，保证低优先级任务最终能够持续取得进展。

## H. 不同角色怎么读这份文档

| 角色 | 推荐先读 |
|---|---|
| 管理者 / 决策者 | 本节、§1、§29、§33 |
| 产品 / 项目负责人 | 本节、§1、§2、§16、§26、§29 |
| AI / 模型工程师 | §2.2、§2.4、§2.6、§8、§14、§15 |
| GPU / 平台工程师 | §2.3、§2.7、§7、§8、§16、§17、§34 |
| 数据工程师 | §2.5、§9～§13、§34.10、§34.13 |
| 研究人员 | §18～§23、§34.11 |
| 安全 / 治理 | §2.8、§20～§28、§34.2、§34.5、§34.13 |
| UI / UX 设计 | 本节、§1、§2、§25、§26、§31 |

## I. 本文是什么，不是什么

### 本文是

- 功能总纲；
- 架构边界；
- 核心能力地图；
- 生命周期与 Gate 的上位约束；
- 后续模块设计和 UI/UX 的共同输入。

### 本文不是

- 最终数据库 Schema；
- 最终 API OpenAPI 文档；
- Scheduler 算法实现；
- 某个具体框架的安装手册；
- UI 页面稿；
- 一次性要求全部实现的开发任务清单。

因此后续可以逐步实现，但不能在实现过程中破坏本文已经冻结的核心边界。


## J. 五层设计阅读法

为了让同一份总纲既能给人看、又能给工程实现使用，平台设计统一分成五层理解。

### 第 1 层：愿景（Why）

回答：

> 为什么需要这套平台？

目标不是为了“把 GPU 管起来”，而是把 AI 从一次次人工项目，变成可以持续生产能力的工程体系：

```text
算力
+ 模型
+ 数据
+ 实验
+ 服务
+ 研究
+ 治理
        ↓
可持续、可复现、可自动迭代的 AI 能力工厂
```

这一层主要给：

- 管理者；
- 项目负责人；
- 业务负责人；
- 合作单位；
- 新加入项目的人。

### 第 2 层：能力地图（What）

回答：

> 平台总体拥有哪些能力？

先不看具体产品名，可以理解为九组能力：

| 能力域 | 解决的问题 |
|---|---|
| **Compute** | 算力在哪里、是否健康、如何隔离和分配 |
| **Model** | 有哪些模型、有什么能力、是否合格 |
| **Data & Knowledge** | 数据从哪里来、质量如何、如何形成知识和训练集 |
| **Experiment & Training** | 如何训练、量化、复现、比较和优化 |
| **Serving** | 如何把能力稳定地提供给业务 |
| **Scheduler** | 业务与训练如何共享资源并自动弹性 |
| **Agent Automation** | 哪些复杂步骤由 Agent 自动规划和协调 |
| **Research & Innovation** | 如何吸收新技术、形成论文/专利/软著 |
| **Governance** | 权限、预算、安全、Gate、审计和可追溯性 |

### 第 3 层：典型旅程（How people use it）

回答：

> 人真正使用平台时，从哪里开始、最后得到什么？

核心旅程至少包括：

1. **接入一个模型并上线服务**；
2. **从零建设一个领域 AI**；
3. **复现一篇论文或一个开源项目**；
4. **让训练任务利用业务低谷 GPU**；
5. **处理生产流量激增和自动扩容**；
6. **把一次实验结果升级为正式生产能力**；
7. **从内部成果生成论文 / 专利 / 软著候选材料**；
8. **平台发现新技术并在人工监督下自我升级**。

UI/UX 后续应围绕这些旅程组织，而不是围绕数据库表或技术组件堆菜单。

### 第 4 层：功能域（How the platform is organized）

回答：

> 系统内部由哪些稳定边界组成？

即本文后面的：

- Gateway & Provider；
- Model & Capability；
- Compute & Virtualization；
- Runtime & Plugin；
- Data & Artifact；
- Experiment & Training；
- Scheduler & Placement；
- Governance & Lifecycle；

以及横向：

- Observability & Lineage；
- Agent Control Plane；
- Research / Reproducibility；
- Innovation / IP；
- Platform Evolution。

### 第 5 层：技术 Contract（How it is implemented safely）

回答：

> 每个能力如何变成可执行、可验证、不可随意漂移的工程对象？

包括：

- API Contract；
- Adapter Contract；
- Registry Contract；
- State Machine；
- Policy；
- Resource Contract；
- Experiment Contract；
- Gate；
- Evidence；
- Lease / Fencing；
- Version / Hash / Lineage。

五层关系可以概括为：

```text
愿景
 ↓
能力地图
 ↓
典型旅程
 ↓
功能域
 ↓
技术 Contract
```

上层回答“为什么和做什么”，下层回答“怎样可靠地实现”。

## K. 模型无关、框架无关、厂商无关

平台必须坚持 **Model-Agnostic / Runtime-Agnostic / Provider-Agnostic**。

### 模型不是架构中心

Qwen3.8-27B 是当前真实参考工作负载，但平台不能假定：

- 永远使用 Qwen；
- 永远是纯文本 LLM；
- 永远是 27B 参数规模；
- 永远是单机 8×4090；
- 永远使用同一个 Tokenizer；
- 永远使用 SGLang 或 vLLM；
- 永远只运行本地模型。

未来可能接入：

```text
不同开源模型族
不同商业模型
不同参数规模
不同量化格式
不同模态
不同 Runtime
不同 Provider
不同 GPU / CPU / Accelerator
```

这些变化原则上只应增加：

```text
Asset
+ Capability
+ Adapter
+ Environment Profile
+ Benchmark
+ Gate
```

而不是修改核心平台架构。

### 平台真正识别的是 Capability

例如业务请求：

```text
coding
reasoning
vision
asr
embedding
video_understanding
image_generation
auto
```

平台再根据：

- Quality；
- SLA；
- Cost；
- Privacy；
- Availability；
- Hardware Fit；
- Runtime Compatibility；
- Current Load；

选择实际模型和 Provider。

因此：

> **模型是可替换实现，Capability 才是长期稳定接口。**

## L. 从“模型平台”进一步理解为“AI 能力工厂”

从人的角度，平台最终不是一个模型仓库，而是一条能力生产线：

```text
外部世界
论文 / 项目 / 模型 / 数据 / 业务需求
                ↓
            Discover
                ↓
     Reproduce / Curate
                ↓
          Evaluate
                ↓
          Optimize
                ↓
          Integrate
                ↓
            Deploy
                ↓
           Production
                ↓
        Feedback / Evidence
                ↓
           Innovate
                ↓
论文 / 专利 / 软著 / 新能力
                ↓
         下一轮 Discover
```

因此同一套基础设施既可以服务：

- 通用大模型；
- 编程模型；
- 视觉模型；
- 语音模型；
- OCR；
- 视频分析；
- Embedding / Reranker；
- 领域模型；
- 多模型 Agent；
- 未来尚未出现的新模型形态。

## M. 功能地图：人看一眼应知道“有什么”

### 1. 算力与环境

```text
节点发现
GPU/CPU/RAM/NVMe 盘点
硬件健康
温度/功耗
Topology
VM
Container
Driver/CUDA Environment
隔离
资源池
```

### 2. 模型与运行

```text
模型导入
模型验证
Capability Probe
Runtime 适配
量化
Deployment
副本
统一逻辑模型
本地/云路由
```

### 3. 数据与知识

```text
外部采集
文件导入
OCR/ASR
清洗
去重
标注
Ontology
知识抽取
Synthetic Dataset
Gold Set
RAG Knowledge Base
```

### 4. 实验与训练

```text
Baseline
Experiment Contract
训练
微调
量化
Benchmark
A/B
Ablation
Power Tuning
Pareto
Evidence
```

### 5. 调度与弹性

```text
Priority
Service Class
Admission
Queue
Fair Share
Gang
Elastic
Checkpoint
Preemption
Training Debt
Reservation
Backfill
Autoscaling
Scale-to-Zero
Cloud Burst
```

### 6. 生产服务

```text
Unified API
Auth
Quota
Rate Limit
Shadow
Canary
Progressive Rollout
Rollback
SLA
Observability
```

### 7. 自动化与 Agent

```text
Goal
Plan
Tool Calling
Execution
Observation
Diagnosis
Retry
Proposal
Human Gate
Continuous Loop
```

### 8. 科研与创新

```text
Technology Radar
论文/项目发现
复现
文献与证据
Ablation
研究报告
论文草稿
专利候选
软著候选
成果资产库
```

### 9. 治理与安全

```text
RBAC
Service Account
Secret
Policy
Budget
Data Classification
Supply Chain
Audit
Backup/DR
Gate
Lineage
IP Gate
```

## N. 平台成熟度不是“一次做完”

总体功能设计是长期能力边界，不代表第一版全部实现。

建议后续实施按成熟度理解：

### Stage 0 — Reference Workload

当前真实 Qwen3.8 / 8×4090 实验继续提供：

- Benchmark；
- Environment；
- Artifact；
- Quantization；
- Power；
- Scheduler；

首批真实 Evidence。

### Stage 1 — Foundation

先建设最小平台骨架：

- Registry；
- Resource Inventory；
- Environment；
- Plugin Contract；
- Unified API；
- Basic Scheduler；
- Gate / Evidence。

### Stage 2 — Engineering Platform

增加：

- Training；
- Quantization；
- Data Factory；
- Auto Benchmark；
- Deployment Lifecycle；
- Autoscaling。

### Stage 3 — Autonomous Platform

增加：

- Agent Control Plane；
- AutoLab；
- Data Acquisition；
- Synthetic Dataset；
- Technology Radar；
- Automatic Reproduction。

### Stage 4 — Innovation Platform

增加：

- Research Evidence Graph；
- Publication Builder；
- IP Workspace；
- Platform Evolution Controller；
- 更高级多节点与跨 Provider 调度。

因此后续开发应：

> **先保证骨架正确，再逐步让自动化和智能化越来越深。**

---

## 0. 文档目的

本项目从“Qwen3.8-27B 在 8×RTX4090 上的推理、量化、训练、Benchmark 与部署优化工程”，演进为一个：

> **开源优先、插件化、本地优先、Agent-Native、可验证、可治理、可持续进化的 AI Compute & Model Engineering Platform。**

平台目标不是绑定某一个模型、某一个推理框架、某一个训练框架或某一个 GPU 环境，而是统一承载：

- 本地模型与外部模型 Provider；
- LLM / VLM / ASR / TTS / OCR / Embedding / Reranker / 图像 / 视频 / 多模态模型；
- 推理、训练、量化、Benchmark、数据处理、自动实验；
- GPU / CPU / RAM / NVMe / Network / Power 等计算资源；
- Driver / CUDA / Runtime / Container / VM 等运行环境；
- Dataset / Model / Runtime / Environment / Experiment / Evidence 的完整版本化与 Lineage；
- 统一 API Gateway 与多能力组合编排；
- 业务优先、训练公平、弹性扩缩、抢占恢复、Backfill、Scale-to-Zero；
- 外部技术发现、论文/项目复现、内部优化、成果应用、论文/专利/软著沉淀；
- 在 Policy、Budget、Gate 和人工监督下的平台自我迭代。

---

# 1. 总体闭环

平台总闭环冻结为：

```text
Discover
  ↓
Reproduce
  ↓
Evaluate
  ↓
Curate
  ↓
Optimize
  ↓
Integrate
  ↓
Deploy
  ↓
Innovate
  ↓
Feedback
  └──────────────→ Discover
```

中文含义：

1. **Discover / 信息采集**  
   发现论文、项目、模型、数据集、框架、Provider、驱动、Kernel、训练方法、量化方法与业务知识。

2. **Reproduce / 复现**  
   在隔离环境中按固定 Contract 重现论文、项目、模型或算法结果。

3. **Evaluate / 测试评估**  
   评估质量、性能、显存、延迟、吞吐、功耗、稳定性、安全性、成本与 SLA。

4. **Curate / 整理治理**  
   完成数据采集、解析、清洗、去重、标注、知识抽取、版本化、证据整理与 Lineage。

5. **Optimize / 优化提升**  
   进行量化、微调、训练、参数搜索、Runtime 调优、GPU 调度优化、数据优化。

6. **Integrate / 整合**  
   将通过验证的新能力接入 Plugin / Adapter / Registry / Gateway。

7. **Deploy / 应用**  
   进入 Canary / Production，通过统一 API 对内或对外提供服务，支持弹性副本和资源动态调度。

8. **Innovate / 创新**  
   从实验和生产中识别新的方法、组合、调度策略、数据方法和技术成果，形成论文、专利、软著、技术报告、开源项目或 Know-how。

9. **Feedback / 反馈**  
   将生产指标、失败样本、知识缺口、资源利用和业务需求重新送回下一轮 Discover / Optimize。

该闭环同时形成一条 **Evidence Chain**：

```text
Source
→ Reproduction Contract
→ Experiment
→ Benchmark Evidence
→ Dataset/Artifact Version
→ Candidate
→ Gate
→ Deployment
→ Production Evidence
→ Achievement / Feedback
```

---

# 2. 总体架构：8 个控制域 + 横向能力

## 2.1 Gateway & Provider Plane

职责：

- 对外提供统一 API；
- 屏蔽内部模型、Runtime、GPU、端口与 Provider 差异；
- 接入本地模型和外部 Provider；
- 进行能力路由、权限、Quota、Rate Limit、审计和 Cloud Burst；
- 支持逻辑模型名，而不是要求业务绑定具体模型。

外部推荐只依赖：

```text
https://<gateway>/v1
```

逻辑模型示例：

```text
coding
general
reasoning
vision
meeting-assistant
asr
embedding
auto
```

外部调用者不需要知道：

- 实际模型名称；
- SGLang / vLLM / llama.cpp；
- GPU 编号；
- 内部端口；
- Local / Bailian / Volcano / 其他 Provider；
- 量化 Profile；
- 实际副本数量。

Provider 策略支持：

```text
LOCAL_ONLY
CLOUD_ONLY
LOCAL_FIRST
CLOUD_FIRST
AUTO
```

所有 Provider 通过 `ProviderAdapter` 接入。

---

## 2.2 Model & Capability Plane

平台不以“模型品牌”为核心，而以 **Capability** 为核心。

支持的模型/能力类型至少包括：

- LLM
- VLM
- ASR
- TTS
- OCR
- Embedding
- Reranker
- Image Generation
- Video Generation
- Audio Generation
- Detection
- Segmentation
- Tracking
- Classification
- Reward / Judge Model
- Multimodal Model

能力描述示例：

```yaml
capabilities:
  input:
    - text
    - image
  output:
    - text
  tasks:
    - vision_understanding
    - ocr
    - document_qa
  features:
    streaming: true
    tool_calling: true
    tensor_parallel: true
    lora: true
```

上层请求可指定：

- 明确能力；
- 逻辑模型；
- `auto` 自动规划。

---

## 2.3 Compute & Virtualization Plane

统一纳管：

- GPU
- CPU
- RAM
- NVMe
- Network
- PCIe / NUMA 拓扑
- Power
- Temperature
- Fan telemetry
- Clock / P-State
- GPU Health

虚拟化路线冻结为：

```text
Linux Host
  ↓
KVM / QEMU / libvirt
  ↓
VM
  ↓
OCI Container Runtime
  ↓
NVIDIA Device Injection
  ↓
Deployment Unit
```

职责边界：

- **VM**：隔离 Kernel / NVIDIA Driver / 强风险边界；
- **Container**：隔离 CUDA userspace / PyTorch / Runtime / Python 依赖；
- **Deployment Unit**：隔离具体模型、资源、网络、Secret、Cache、Artifact；
- **Quarantine VM**：承载未知代码、未知模型、自定义 CUDA 扩展等高风险对象。

RTX4090 第一阶段采用 **Whole-GPU / Exclusive 为生产默认**，共享能力必须经过 Benchmark Gate 后开放。

---

## 2.4 Runtime & Plugin Plane

核心原则：

> **Core owns policy and authority; plugins provide capability.**

核心平台不直接绑定任何具体技术实现。

统一插件契约包括：

- `ProviderAdapter`
- `InferenceRuntimeAdapter`
- `TrainingRuntimeAdapter`
- `QuantizationAdapter`
- `DataProcessingAdapter`
- `AnnotationAdapter`
- `VisionAdapter`
- `BenchmarkAdapter`
- `CacheAdapter`
- `StorageAdapter`
- `ContainerRuntimeAdapter`
- `VirtualizationAdapter`
- `SchedulerBackendAdapter`
- `ObservabilityAdapter`

推理 Runtime 示例：

```text
InferenceRuntime
├── SGLangAdapter
├── VLLMAdapter
├── LlamaCppAdapter
├── TensorRTLLMAdapter
└── FutureAdapter
```

训练 Runtime 示例：

```text
TrainingRuntime
├── TransformersTrainer
├── TRL
├── Axolotl
├── LLaMAFactory
├── DeepSpeed
├── Megatron
└── FutureFramework
```

所有 Plugin 必须：

- Manifest；
- Capability Probe；
- API Version；
- Compatibility Gate；
- Quarantine / Candidate / Active 生命周期；
- 不直接拥有核心 Authority。

---

## 2.5 Data & Artifact Plane

该 Plane 负责：

- Source Registry
- Dataset Registry
- Artifact Registry
- Data Recipe Registry
- Annotation Schema Registry
- Ontology Registry
- Knowledge Base
- Model Weights
- LoRA / Checkpoint
- Quantized Weights
- Container Image Metadata
- VM Image Metadata
- Benchmark Evidence
- Dataset Snapshot
- Cache Metadata

核心原则：

> 数据不是几个 JSONL；模型也不是几个权重文件。

Dataset 资产必须至少包含：

```text
Data
+ Version
+ Time
+ Provenance
+ License
+ Quality
+ Usage Policy
+ Immutable Hash
```

Model 资产必须至少包含：

```text
Base Model
+ Training Data
+ Training Config
+ Code
+ Environment
+ Evaluation
+ Gate Evidence
```

---

## 2.6 Experiment & Training Plane

统一管理：

- 推理实验
- Quantization
- Fine-tune
- LoRA / QLoRA
- SFT
- Continued Pretraining
- Preference Optimization
- Benchmark
- Runtime tuning
- Scheduler simulation
- Power tuning
- Data experiment
- Reproduction experiment
- Ablation

所有实验必须通过 `Experiment Contract`：

```yaml
goal: ...
baseline: ...
candidate: ...

resources:
  gpu_max: ...
  wall_time_max: ...

allowed_changes:
  - ...

forbidden_changes:
  - benchmark_dataset
  - acceptance_threshold
  - baseline_result

acceptance:
  quality: ...
  performance: ...
  resource: ...

on_success: ...
on_failure: ...
```

AI 可以提出 Experiment Proposal，但不能：

- 修改冻结 Benchmark；
- 降低 Gate；
- 覆盖 Baseline；
- 删除失败证据；
- 擅自突破 Budget / Policy。

---

## 2.7 Scheduler & Placement Plane

这是平台运行核心。

Scheduler 不只调 GPU，而是统一调度：

```text
GPU
VRAM
CPU
RAM
NVMe IO
Network
Power
Topology
Loaded Model Affinity
Cache Affinity
SLA
Queue
```

调度总原则：

> **Business-SLA-First, Fair-Share, Preemptive, Work-Conserving Scheduling**

即：

- 业务 SLA 优先；
- 训练和测试不能永久饿死；
- 只要存在可执行工作，就尽量不让 GPU 空闲；
- 业务下降时，空闲资源自动转给训练、Benchmark、AutoLab、数据处理；
- 业务上涨时，低优先级工作通过降级、checkpoint、迁移、暂停释放资源。

优先级冻结为：

```text
P0 CRITICAL      核心在线业务
P1 INTERACTIVE   普通在线推理 / ASR / VLM
P2 IMPORTANT     有时限验收 / Benchmark / 紧急实验
P3 BATCH         训练 / 微调 / 量化 / 大规模测试
P4 OPPORTUNISTIC 自动研究 / 数据清洗 / 非紧急实验
```

必须支持：

### Admission Control

```text
Request
→ Policy
→ Admission
   ├─ ADMIT
   ├─ QUEUE
   ├─ CLOUD
   └─ REJECT
```

### Gang / Atomic Scheduling

多卡任务 All-or-Nothing，不允许只占一部分 GPU 后等待其余资源。

### Elastic Resource Contract

```yaml
gpu:
  min: 2
  preferred: 4
  max: 8
elastic: true
```

### Multi-Resource Fair Share

不能只按 GPU 数量计算公平性，还必须考虑 RAM、VRAM、CPU、IO、Network、Power。

### Priority Aging

等待越久，低优先级任务有效优先级逐步提高，避免永久饥饿。

### Training Debt / Soft Guarantee

训练可定义滚动 24h 的 GPU-hour 目标；白天因业务被挤压形成 Training Debt，低谷期自动偿还。

### Preemption Cost

抢占决策考虑：

- checkpoint_age
- checkpoint_cost
- restart_cost
- progress
- model_load_cost
- minimum_run_window
- preemption_count

### Backpressure

在线队列必须有界；不能无限堆请求直到 KV / VRAM / P95 全部失控。

### Reservation + Backfill

未来需要整块 GPU 时允许预约；预约前的碎片时间允许短任务 Backfill，但不得推迟预约任务。

### Failure Domain

支持：

- Affinity
- Anti-Affinity
- Node / VM / PCIe Root / Rack 等 Fault Domain；
- 生产副本避免集中于同一故障域。

### GPU Health Drain

```text
READY
→ DEGRADED
→ DRAIN
→ QUARANTINED
→ DIAGNOSTIC
→ READY
```

异常 GPU 不允许继续接收新任务。

### HOT / WARM / COLD

```text
HOT  模型已在 GPU
WARM Runtime/权重已准备
COLD 完整冷启动
```

用于降低大模型冷启动成本。

### Scale-to-Zero

低频能力允许：

```text
0 replicas
→ 请求到达
→ Activation Queue
→ Auto Load
→ Serve
→ Idle
→ Auto Unload
```

### Autoscaling

依据：

- RPS
- Queue Length
- Concurrent Requests
- TTFT
- TPOT
- P95/P99
- GPU Util
- VRAM
- KV Pressure
- Replica Health

支持：

- Scale Out：增加副本；
- Scale Up：改变 Resource Profile；
- Predictive Warmup；
- Hysteresis / Cooldown；
- 扩容积极、缩容保守。

---

## 2.8 Governance & Lifecycle Plane

统一负责：

- Authority
- Policy
- Gate
- Identity / RBAC
- Service Account
- Secret
- Quota
- Budget
- Audit
- Supply Chain Security
- License
- Backup / DR
- Upgrade / Rollback
- Publication/IP Gate
- Human Approval

数据分级至少支持：

```text
PUBLIC
INTERNAL
CONFIDENTIAL
RESTRICTED
```

Provider Routing 必须服从数据分级；例如 CONFIDENTIAL / RESTRICTED 不允许因为 GPU 满载就自动发往未经授权的外部 Provider。

---

# 3. 横向能力：Observability & Lineage

所有核心组件统一产生：

- Trace
- Metric
- Log
- Event

每一个生产请求可以追踪：

```text
Gateway
→ Policy
→ Router
→ Scheduler
→ Queue
→ Runtime
→ GPU
→ Response
```

所有资产必须可追溯：

```text
Production Alias
→ Model Profile
→ Training Run
→ Dataset Version
→ Base Model
→ Runtime
→ Environment
→ Benchmark
→ Gate Evidence
```

这条 Lineage 是平台 Authority 的核心组成部分。

---

# 4. Agent Control Plane

平台采用 **Agent-Native**，但 Agent 不拥有核心 Authority。

原则：

> **Agents drive the workflow; the platform controls authority.**

Agent 适合承担：

- Source Discovery
- Research
- Knowledge Gap Analysis
- Cleaning Strategy
- Annotation Planning
- Ontology Mapping
- Synthetic Data Generation
- Training Strategy
- Experiment Planning
- Failure Diagnosis
- Benchmark Analysis
- Optimization Proposal
- Research / Reproduction Planning

确定性组件承担：

- SHA / Hash
- 去重
- GPU Lease
- Resource Allocation
- 权限判断
- Quota
- Version
- Metric
- Gate Threshold
- Checkpoint
- Artifact Storage

Agent 只能通过 Platform Tool API：

```text
source.search
source.crawl
document.parse
dataset.clean
dataset.label
dataset.freeze

model.download
model.inspect
model.quantize

training.plan
training.start
training.pause
training.resume

benchmark.run
gate.evaluate

gpu.reserve
deployment.create
deployment.scale
```

禁止 Agent 直接无约束执行宿主命令、任意访问 Secret、修改 Gate 或更改 Authority。

---

# 5. 多模态能力编排

统一 API 可以在一次逻辑请求中组合多个专精能力。

示例：

```text
Video
 ├─ Audio → ASR
 ├─ Frames → VLM
 ├─ OCR
 ├─ Detection / Tracking
 └─ Speaker Diarization
          ↓
      LLM Reasoner
          ↓
    Unified Response
```

因此平台对外可以表现为“一个多模态模型”，内部实际是：

- 多模型；
- 多 Runtime；
- 多 Provider；
- 多 GPU；
- 多阶段 DAG。

核心组件：

- Capability Registry
- Capability Graph
- Planner
- Workflow / DAG Executor
- Multimodal Composer

---

# 6. 模型 Deployment Unit

模型不是“直接跑在 GPU 上”，而是运行在受控的 Deployment Unit 中。

```yaml
deployment:
  id: coding-prod-v7

model:
  artifact: ...
  hash: ...

runtime:
  engine: ...
  image: ...

environment:
  profile: ...

isolation:
  profile: ...

resources:
  gpu_count: ...
  gpu_exclusive: ...
  cpu: ...
  memory: ...

network:
  internet: false

secrets:
  allowed: []

storage:
  model: read_only
  cache: private

policy:
  production: true
```

Isolation Profile：

```text
L1 Shared       已信任轻量模型
L2 Standard     正常生产模型
L3 Strong       Candidate / 自定义代码
L4 Quarantine   未知模型 / 未知代码
```

---

# 7. GPU Memory & Placement Manager

允许“一张 GPU 承载多个可信 Deployment Unit”，但不能简单依据 `nvidia-smi free memory`。

显存模型至少包含：

```text
Weights
CUDA Context
Runtime Base
KV Cache
Activations
Workspace
Temporary Buffer
Fragmentation
Safety Headroom
```

每个 Model Profile 建立：

- current_vram
- reserved_vram
- peak_vram
- recommended_reservation
- safety_headroom
- compute profile
- power profile

支持：

- VRAM Accounting
- Reservation
- Headroom
- Bin Packing
- Fragmentation Awareness
- Workload Consolidation
- Auto Load / Unload
- Hot / Warm / Cold
- Preemption
- Shared GPU（受 Gate 控制）
- MPS（实验能力，不作为安全边界）

生产大模型默认 Exclusive；小型可信 Embedding / Reranker / ASR 可在验证后共享。

---

# 8. 物理环境与 Environment Registry

Environment 是一级资产。

至少记录：

```text
Host OS
Kernel
BIOS
CPU
RAM
GPU
NVIDIA Driver
CUDA
cuDNN
NCCL
PyTorch
Container Image
Runtime
Power Profile
Topology
```

实验记录必须引用：

```text
model_profile
+ runtime_profile
+ environment_profile
+ benchmark_version
```

Driver / Kernel 变化通过 VM 隔离；CUDA userspace / PyTorch / Runtime 变化通过 Container 隔离。

Environment 必须支持：

```text
Stable
Candidate
Experimental
Deprecated
Retired
```

任何 Driver / CUDA / Runtime 升级都走：

```text
Candidate
→ Compatibility
→ Smoke
→ Benchmark
→ Stability
→ Regression
→ Gate
→ Promote / Rollback
```

---

# 9. Dataset Lifecycle

Dataset 状态：

```text
DISCOVERED
→ INGESTED
→ QUARANTINED
→ CLEANED
→ ANNOTATED
→ VALIDATED
→ APPROVED
→ FROZEN
→ DEPRECATED
→ RETIRED
```

质量等级独立：

```text
D0 Raw
D1 Clean
D2 Verified
D3 High Quality
D4 Gold
D5 Benchmark Only
```

用途权限独立：

```text
TRAIN
VALIDATION
TEST
BENCHMARK
JUDGE
DISTILLATION
RAG
ARCHIVE
```

Dataset 必须包含时间属性：

- created_at
- collected_at
- valid_from
- valid_until
- knowledge_cutoff
- last_reviewed_at

质量不能只用单一总分，至少拆分：

- factual_accuracy
- label_accuracy
- source_trust
- completeness
- freshness
- consistency
- duplication
- contamination
- security / PII

支持 Dataset Aging 与 Freshness Policy：不同领域采用不同时间衰减策略。

---

# 10. Data Acquisition Plane

数据不一定已经存在；平台需要具备“从零建设领域数据集”的能力。

统一 Source Registry，来源可包括：

- Web
- RSS
- API
- Database
- File
- PDF / DOC / PPT / XLS
- Image
- Audio
- Video
- Subtitle
- Internal Archive

所有采集任务必须记录：

- source
- publisher
- captured_at
- published_at
- authority_level
- license / copyright status
- robots / access policy
- language
- topic
- hash

采集能力通过 Adapter 接入，核心只管理 Source Authority、Policy、Snapshot、Lineage。

---

# 11. Data Factory

数据处理链：

```text
Raw
→ Quarantine
→ Parse / OCR / ASR
→ Normalize
→ Clean
→ Deduplicate
→ Filter
→ Enrich
→ Auto Annotation
→ Human Review
→ Quality Audit
→ Data Gate
→ Frozen Dataset
```

开源工具作为 Worker / Plugin，不作为 Authority。

候选能力类别：

- 通用数据清洗；
- GPU 加速多模态整理；
- OCR / ASR；
- 文本标注；
- CV / 视频标注；
- Detection / Segmentation / Tracking；
- Label Quality；
- Active Learning；
- Human-in-the-loop。

平台内部使用自己的 Canonical Annotation Schema，再通过 Adapter 导出 YOLO / COCO / CVAT / Label Studio / MOT / 自定义格式。

自动标注必须记录：

- annotation source；
- model / human；
- model revision；
- confidence；
- reviewer；
- pipeline version。

---

# 12. Knowledge Engineering

“拥有资料”不等于“拥有可训练知识”。

平台需要：

- Fact / Claim Extraction
- Entity Resolution
- Timeline
- Relation Extraction
- Knowledge Object
- Ontology
- Knowledge Conflict
- Source Citation
- Evidence Span

Domain Ontology 必须版本化。

原始领域资料可派生为：

```text
RAG Knowledge Base
Continued Pretraining Corpus
SFT Dataset
Preference Dataset
Benchmark / Gold Set
```

训练前必须由 Training Strategy Planner 判断：

```text
知识补充        → RAG
行为/表达提升   → SFT / LoRA
大量领域语料    → Continued Pretraining
偏好/行为约束   → Preference Optimization
基础能力不足    → 更换 Base Model
```

---

# 13. Synthetic Dataset Factory

当没有合适训练集时，平台允许“制造训练集”。

流程：

```text
Source Documents
→ Knowledge Extraction
→ Teacher Model
→ Candidate QA / Instruction
→ Fact Verification
→ Source Alignment
→ Dedup
→ Difficulty Classification
→ Quality Score
→ Human Sampling
→ Dataset Gate
```

本地模型优先作为 Teacher；外部 API 仅在 Policy 允许且确有必要时作为辅助 Teacher / Judge。

---

# 14. Model Lifecycle

模型生命周期：

```text
DISCOVERED
→ DOWNLOADED
→ QUARANTINED
→ VERIFIED
→ BASELINED
→ CANDIDATE
→ OPTIMIZED / FINETUNED
→ QUALIFIED
→ STAGING
→ PRODUCTION
→ DEPRECATED
→ RETIRED
```

核心规则：

> **FINETUNED ≠ QUALIFIED。**

训练完成只是产生 Candidate Artifact，必须重新通过：

- Functional Gate
- Quality Gate
- Security Gate
- Performance Gate
- Stability Gate
- Resource Gate
- Canary Gate

生产别名只允许指向 QUALIFIED / STAGING / PRODUCTION 对象。

---

# 15. Model Gate Pipeline

建议基础门禁：

```text
G0 Artifact Gate
G1 Compatibility Gate
G2 Functional Gate
G3 Quality Gate
G4 Safety / Security Gate
G5 Performance Gate
G6 Stability Gate
G7 Resource / Efficiency Gate
G8 Canary Gate
```

不使用单一“总分”决定模型是否合格。

按 Profile Contract 定义：

- Quality
- Latency
- Throughput
- VRAM
- Power
- Stability
- Compatibility
- Safety
- Cost

不同逻辑模型可拥有不同 Contract，例如 `coding-fast`、`coding-quality`。

---

# 16. Online 与 Batch

系统必须区分：

## Online

- Chat
- Coding API
- realtime ASR
- VLM
- Gateway 服务

特征：

- SLA；
- 低延迟；
- 不轻易中断；
- 高优先级。

## Batch

- Training
- Quantization
- Benchmark
- Data Processing
- Video Generation
- AutoLab

特征：

- 可排队；
- 部分可抢占；
- 可 checkpoint；
- 适合吃剩余资源。

统一资源池，不永久划分“业务 GPU”与“训练 GPU”。

业务少时，训练/测试/数据任务可自动使用全部剩余资源；业务增加时资源向 Online 倾斜。

---

# 17. Scheduler HA 与控制面可靠性

Scheduler 自身不能成为单点。

必须采用：

```text
Desired State
+ Durable State
+ Lease
+ Fencing Token / Epoch
+ Idempotent Reconcile
+ Watchdog
+ Progress Invariant
```

必须维护至少五本账：

1. Resource Ledger
2. Allocation / Lease Ledger
3. Quota / Fair-Share Ledger
4. Reservation Ledger
5. Checkpoint / Progress Ledger

Scheduler 重启后必须通过 Actual State Reconciliation 恢复，而不是仅相信数据库记录。

---

# 18. Research & Reproducibility Workspace

目标：

```text
Paper → Run
Run → Paper
```

包括：

- Paper / Research Registry
- Technology Radar
- Research Agent
- Reproduction Contract
- Reproduction Engine
- Prior-art / project comparison
- Ablation
- Research Evidence Graph
- Publication Builder

论文/项目生命周期：

```text
DISCOVERED
→ SCREENED
→ RELEVANT
→ REPRODUCIBLE
→ REPRODUCED
→ VALIDATED / NOT_REPRODUCED
→ ADOPTED / ARCHIVED
```

复现不是直接 clone + run，而是：

```text
Paper / Project
→ Commit Pin
→ License
→ Dependency / Supply Chain Scan
→ Quarantine
→ Environment Build
→ Reproduction Contract
→ Experiment
→ Benchmark
→ Evidence
```

平台应回答：

> “论文结论在我们的硬件、模型、数据和 Runtime 上是否成立？”

---

# 19. Publication Builder

内部实验可自动形成：

- Internal Research Note
- Benchmark Report
- Technical Report
- White Paper
- Academic Manuscript Draft
- Presentation Material
- Web Report
- Reproducibility Package

生成原则：

> **Evidence First。**

论文/报告中的 Methods、Results、Table、Figure、Appendix 尽量由 Registry 与 Experiment Evidence 自动生成。

任何 Claim 必须可以解析到：

```text
Claim
→ Experiment IDs
→ Result
→ Statistical Check
→ Citation / Evidence
```

无证据的 Claim 标记为 UNSUPPORTED，不允许进入正式发布。

---

# 20. Innovation & IP Workspace

从研发和实验中自动识别：

- Patent Candidate
- Software Copyright Candidate
- Paper Candidate
- Open Source Candidate
- Internal Know-how
- Trade Secret Candidate

成果生命周期：

```text
DISCOVERED
→ EVIDENCED
→ SCREENED
→ CLASSIFIED
→ DRAFTED
→ HUMAN REVIEW
→ FILED / PUBLISHED
→ GRANTED / ARCHIVED
```

系统可以自动整理：

## 软件著作权候选材料

- 软件名称
- 版本号
- 功能说明
- 技术特点
- 运行环境
- 架构说明
- 使用手册
- 截图
- Release / Commit Evidence
- 代码材料候选

## 专利候选材料

- 技术问题
- 技术方案
- 系统框图
- 流程
- 实施例
- Benchmark 技术效果
- 现有技术 / Prior Art
- 技术交底书
- 摘要
- 权利要求草案

最终法律申报、署名、公开和权利范围由人确认。

---

# 21. Publication / IP Gate

任何准备公开的：

- 论文
- GitHub 项目
- White Paper
- 技术报告
- Demo
- 博客

都必须先经过：

```text
IP Opportunity Detection
→ Prior-Art / Patent Screening
→ Human Decision
→ Public Release
```

防止具有潜在专利价值的技术在申请前被无意公开。

---

# 22. Platform Evolution Controller

平台可以自动发现并验证新的能力，但不同级别采用不同 Release Authority。

## Level A：能力插件

例如：

- 新 SGLang
- 新 vLLM
- 新 ASR
- 新 VLM
- 新 Cleaner

允许高度自动：

```text
Discover
→ Quarantine
→ Probe
→ Benchmark
→ Candidate
→ Canary
→ Promote
```

## Level B：策略与算法

例如：

- Scheduler v2
- Router v3
- Autoscaler v4

允许自动：

- Proposal
- Code
- Simulation
- Test
- Shadow

但 Production Promotion 需要 Human Gate。

## Level C：核心 Authority

例如：

- 权限模型
- Gate 规则
- Secret Policy
- Audit Policy
- Production Safety Boundary

必须：

```text
Proposal
→ Human Review
→ Explicit Approval
```

核心 Authority 不允许系统完全自主修改。

---

# 23. Technology Intake & Capability Evolution

生产或实验发现能力缺口：

```text
Capability Gap
→ Technology Radar
→ Papers / Projects / Models
→ Candidate
→ Reproduce
→ Benchmark
→ Gate
→ Integration
→ Canary
→ Human Approval
→ Capability Registry
```

最终形成：

> **持续吸收外界最新技术，在本地复现、验证、优化，并在人的监督下升级平台能力。**

---

# 24. 核心 Registry

逻辑 Registry 冻结为：

- Model Registry
- Dataset Registry
- Artifact Registry
- Runtime Registry
- Environment Registry
- Experiment Registry
- Benchmark Registry
- Provider Registry
- Plugin Registry
- Source Registry
- Ontology Registry
- Research Registry
- Achievement / IP Registry

所有 Registry 对象至少统一具有：

```text
ID
Version
State
Hash
Created At
Source
Lineage
Capabilities
Policy
Gate Status
```

---

# 25. 核心领域对象

为了避免数据模型无限膨胀，核心对象收敛为四类：

## Asset

包括：

- Model
- Dataset
- Weight
- LoRA
- Container Image
- VM Image
- Paper
- Source
- Benchmark Artifact

## Environment

包括：

- Hardware
- Driver
- CUDA
- Runtime
- Container
- OS
- Power Profile

## Deployment

定义：

> 某个 Asset 在某个 Environment 中，以什么 Runtime、Isolation、Resource、Network、Secret Policy 真正运行。

## Experiment

定义：

> 谁在什么 Environment，使用什么 Asset，以什么参数执行什么任务，结果如何，有何 Evidence。

主关系：

```text
Asset
  +
Environment
  ↓
Deployment
  ↓
Experiment
  ↓
Evidence
  ↓
Gate
  ↓
Production / Achievement
```

---

# 26. 自动化等级

平台需要支持：

```text
MANUAL
ASSISTED
GUARDED_AUTO
AUTONOMOUS
```

默认建议：

```text
GUARDED_AUTO
```

即：

- Agent 自动规划；
- 系统自动执行；
- 普通失败自动恢复；
- 关键 Gate / Budget / Security / Authority 变化找人。

人的主要职责收敛为：

- Goal
- Policy
- Budget
- Security Boundary
- Acceptance Criteria
- Final Approval

---

# 27. 统一成本与资源账本

所有任务统一记录：

- GPU seconds / GPU-hours
- Energy / kWh
- CPU time
- RAM
- Storage
- IO
- Network
- External API Tokens
- External Provider Cost

支持指标：

- Cost / 1M tokens
- Energy / 1M tokens
- Quality / Cost
- Quality / kWh

自动实验必须接受 Budget Governor 约束，例如：

```yaml
autolab:
  max_gpu_hours_per_day: ...
  max_power_kwh_per_day: ...
  max_external_api_cost: ...
  max_parallel_experiments: ...
```

---

# 28. Backup / DR

必须优先保护：

- Registry Metadata
- Lineage
- Experiment Evidence
- Dataset Version Metadata
- Gate Evidence
- Policies
- Environment Definitions
- Deployment Definitions

模型权重很多可以重新下载，但 Lineage 和证据一旦丢失很难重建。

要求：

- Metadata Backup
- Artifact Backup Policy
- Restore Test
- Environment Rebuild Test
- Disaster Recovery Evidence

---

# 29. Reference Workloads

## Reference Workload #001

`Qwen3.8-27B × 8×RTX4090`

重点验证：

- Runtime
- Quantization
- Benchmark
- GPU Scheduler
- VRAM
- Power
- Pareto
- Model Gate
- Environment Gate

当前 Phase 04 产生的质量、显存、吞吐、功耗和 Gate Evidence 应逐步转化为平台首批真实资产。

## Reference Domain Project #002

领域模型工厂（可使用“沂蒙精神领域 AI”作为真实示范项目之一）。

重点验证：

- Source Discovery
- Acquisition
- Document Intelligence
- OCR / ASR
- Cleaning / Dedup
- Annotation
- Knowledge Engineering
- Ontology
- Synthetic Dataset
- RAG / SFT / LoRA / CPT Strategy
- Domain Gold Benchmark
- Model Gate
- Unified API
- Continuous Update
- Research / Publication / IP

---

# 30. 未来实施原则

## 30.1 第一原则：先 Contract，后实现

现在不要求 v1 一次实现所有高级能力，但：

- 数据模型；
- 状态机；
- Adapter Contract；
- Registry Contract；
- Scheduler Contract；
- Gate Contract；

必须为后续演进留出空间。

## 30.2 第二原则：先 Native，后大集群

当前 8×4090 单机优先实现 Native Scheduler。

未来多节点再通过 Adapter 接入：

- Slurm
- Kubernetes
- Kueue
- Ray
- 其他成熟调度后端

核心平台不能绑定其中任何一种。

## 30.3 第三原则：不重复造成熟轮子

可以嫁接成熟开源能力，但所有第三方能力必须是：

> **Worker / Plugin，而不是 Authority。**

Authority 永远留在平台自己的：

- Registry
- Policy
- Scheduler
- Gate
- Lineage
- Audit

## 30.4 第四原则：开放能力，不开放权力

Plugin / Agent 可以提供能力和 Proposal，但不能直接修改：

- Authority
- Gate
- Policy
- Secret Scope
- Production Safety Boundary

---

# 31. 当前明确不在本文展开的内容

以下内容进入下一阶段设计：

1. 用户角色矩阵；
2. Human-AI Responsibility Matrix；
3. Information Architecture；
4. Golden Journeys；
5. Navigation；
6. Dashboard；
7. Human Inbox；
8. Agent Copilot；
9. Model / Data / Training / Compute 工作台；
10. Wireframe；
11. Design System；
12. Mobile Interaction；
13. Usability Gate。

这些统一进入后续：

> **UI / UX / Human-AI Interaction Architecture**

---

# 32. 后续文档拆分建议

本文冻结后，后续可按需要拆分为：

```text
docs/design/
├── 00-FUNCTIONAL-ARCHITECTURE.md        ← 本文
├── 01-DOMAIN-MODEL.md
├── 02-GATEWAY-PROVIDER-CONTRACT.md
├── 03-COMPUTE-RUNTIME-ARCHITECTURE.md
├── 04-SCHEDULER-CONTRACT.md
├── 05-DATA-FACTORY.md
├── 06-MODEL-LIFECYCLE.md
├── 07-EXPERIMENT-AUTOLAB.md
├── 08-AGENT-CONTROL-PLANE.md
├── 09-RESEARCH-IP.md
├── 10-GOVERNANCE-SECURITY.md
└── ui/
    └── ...                              ← 下一阶段
```

当前阶段只要求保留这一份总纲，后续逐步拆分。

---

# 33. 功能冻结结论

本平台总体定位冻结为：

> **AI Compute & Model Engineering Platform**  
> 一个开源优先、插件化、本地优先、Agent-Native 的 AI 算力、模型工程与持续创新平台。

平台实现从：

```text
信息采集
→ 复现
→ 测试
→ 整理
→ 优化
→ 提升
→ 整合
→ 应用
→ 创新
→ 反馈
```

的持续闭环。

最终目标不是让人每天手工：

- 启动模型；
- 选 GPU；
- 改端口；
- 跑训练；
- 找论文；
- 搬数据；
- 比 Benchmark；
- 调副本；
- 处理闲置算力。

而是让用户主要提供：

```text
Goal
Policy
Budget
Security Boundary
Acceptance Criteria
```

其余流程由：

```text
Agent
+ Deterministic Workers
+ Scheduler
+ Registry
+ Gate
+ Governance
```

在人的监督下自动完成。

---

**本文件作为后续模块拆分、API Contract、Scheduler Contract、Data/Model Lifecycle 以及 UI/UX 设计的上位功能设计输入。**

---

# 34. 功能审计补遗（2026-09-25）

本节用于对照前期完整讨论，显式补齐此前在总纲中仅“隐含覆盖”或未单独列出的功能点。以下内容与前文具有同等设计约束力。

## 34.1 Data Plane 与 Control Plane 明确分离

统一 Gateway 对外至少区分：

### Data Plane

面向业务调用：

```text
/v1/responses
/v1/chat/completions
/v1/embeddings
/v1/audio/transcriptions
/v1/audio/speech
/v1/images/...
/v1/videos/...
/v1/rerank
```

优先兼容主流 OpenAI-style API Contract；业务调用方只依赖统一 Gateway，不依赖内部模型端口。

### Control Plane

面向平台 Web、Agent 与运维：

```text
/api/admin/nodes
/api/admin/gpus
/api/admin/models
/api/admin/runtimes
/api/admin/jobs
/api/admin/scheduler
/api/admin/experiments
/api/admin/providers
/api/admin/datasets
```

Data Plane 与 Control Plane 的认证、权限、Rate Limit、审计和暴露范围必须分离。

## 34.2 Provider 凭据、使用策略与统一评测

外部 Provider 不能只保存一个 API Key。

Provider Registry 还必须记录：

- Provider / Region / Base URL；
- Secret Reference；
- Credential Lifecycle / Rotation；
- Health；
- Capability；
- Model Catalog；
- Usage Plan / 套餐限制；
- License / Terms / Allowed Use；
- Cost；
- Data Classification Eligibility；
- Benchmark / Quality / Latency Evidence。

API Key、Token 等不以明文散落在配置文件中；通过 Secret Store / Secret Broker 引用，按 Workload Identity 最小授权。

外部模型与本地模型一样进入 Benchmark / Gate，可按：

```text
Quality
Latency
Cost
Availability
Privacy
GPU Pressure
```

参与 Router 决策。

## 34.3 Container / Virtualization 后端候选

平台 Contract 不绑定具体实现，但首批候选明确记录为：

```text
ContainerRuntimeAdapter
├── containerd      ← 平台默认候选
├── Podman          ← rootless / 开发与实验候选
└── Docker          ← 兼容模式
```

```text
VirtualizationAdapter
├── libvirt/KVM/QEMU ← 默认底座
├── Incus            ← 可选后端
├── Proxmox           ← 可选后端
└── Future
```

RTX4090 第一阶段不以 vGPU / MIG 为基础假设；Driver 隔离主要依靠 VM + Whole-GPU Passthrough，CUDA userspace 与 Runtime 隔离主要依靠 Container。

## 34.4 Cache Plane 与 KV Cache 生命周期

Cache 是可调度资源，不只是 Runtime 内部细节。

平台预留：

```text
CacheAdapter
├── Runtime Native Cache
├── Multi-tier Cache
└── Future Cache Backend
```

Cache Tier 至少允许：

```text
GPU VRAM
CPU RAM
NVMe
Remote / Shared Cache
```

KV Cache 的复用必须至少校验：

- model_id；
- model_revision；
- tokenizer_hash；
- runtime_version；
- cache_schema / compatibility。

无法证明兼容时默认不复用。

Scheduler 可将 Cache Affinity、Prefix Reuse、Loaded Model Affinity 纳入 Placement Score。

## 34.5 网络隔离与 Secret 隔离

Deployment Unit 默认采用最小网络权限。

逻辑网络域至少包括：

```text
gateway-net
runtime-net
training-net
storage-net
management-net
quarantine-net
```

默认原则：

> East-West traffic = DENY，按 Contract 显式开放。

未知模型 / Quarantine 环境默认：

- 无生产 Secret；
- 无管理网访问；
- 无生产数据库访问；
- 外网按采集/复现 Contract 最小开放。

Secret 使用 Workload Identity + Secret Broker / 短时凭据优先，不允许所有模型共享统一 `.env`。

## 34.6 GPU 主动控制能力模型

硬件纳管不仅包含 telemetry，也预留主动控制。

每项能力必须 Capability Probe，不假定所有 GPU 均支持：

```text
power.read
power.limit
clock.read
clock.lock
fan.read
fan.control
temperature.read
pstate.read
```

特别是消费级 GPU 的主动风扇控制不得视为通用能力。

Power Limit / Clock Profile 可进入 Experiment：

```text
Performance
Balanced
Efficiency
```

通过 Benchmark 自动寻找 TPS / Quality / Energy 的 Pareto 点。

## 34.7 Service Class 与 Priority 分离

Priority 表示“谁先”，Service Class 表示“怎样服务”。

建议至少支持：

```text
REALTIME
INTERACTIVE
STANDARD
BATCH
OPPORTUNISTIC
```

Service Class 可影响：

- Queue Policy；
- Cold Start Policy；
- min_hot / warm_pool；
- SLA；
- Preemption；
- Scale-to-Zero；
- Deadline；
- Cloud Burst。

它与 P0～P4 Priority 独立组合。

## 34.8 Shadow / Canary / Progressive Promotion

Candidate 不能从 Benchmark 直接跳到 100% Production。

至少支持：

```text
Offline Benchmark
→ Shadow
→ Canary
→ Progressive Traffic
→ Production
```

Shadow 模式：

- 复制真实请求到 Candidate；
- Candidate 结果不返回用户；
- 自动比较质量、延迟、错误、资源、工具调用等指标。

Canary 可按策略推进：

```text
1% → 5% → 20% → 50% → 100%
```

任一 Gate 失败可自动 Rollback。

## 34.9 Scheduler Replay / Historical Simulation

新的 Scheduler Strategy 不直接进入生产。

平台保存历史 Job / Request / Resource Timeline，并支持：

```text
Historical Workload
→ Replay
→ Candidate Scheduler
→ Compare
```

比较至少包含：

- GPU utilization；
- average waiting；
- P95/P99；
- energy；
- preemption count；
- starvation；
- deadline miss；
- fragmentation。

同时支持 Workload Consolidation / GPU Defragmentation：在不违反 SLA 和 Gate 的前提下迁移或重启可迁移工作负载，释放完整 GPU / VRAM Capacity。

## 34.10 数据与视觉开源能力候选池

以下均作为 Adapter / Worker 候选，不作为 Authority：

### 数据处理

- Data-Juicer；
- NeMo Curator；
- 未来同类项目。

### 人工标注 / Human-in-the-loop

- Label Studio；
- CVAT；
- Doccano；
- Future Annotation Backend。

### 数据质量

- Cleanlab；
- Rule Engine；
- Local Model Judge。

### Vision Auto Annotation

- Detector Adapter（YOLO / MMDetection / Future）；
- Open-vocabulary detector；
- SAM / SAM2 类 Segmenter；
- Tracker；
- Grounded Detection + Segmentation 组合；
- VLM Auto Labeler。

### 文档解析

- Docling；
- Apache Tika；
- OCR Backend。

### 采集

- Scrapy；
- Crawl4AI；
- API / RSS / DB / File Import Adapter。

第三方工具可以替换、并存或 Ensemble；Canonical Dataset / Annotation Schema / Registry / Lineage 始终由平台掌握。

## 34.11 Research Source Adapter 候选

Technology Radar / Research Agent 可通过 Adapter 接入：

- arXiv；
- Semantic Scholar；
- OpenReview；
- Crossref / DOI metadata；
- GitHub；
- Hugging Face；
- 官方项目与模型站点；
- Future Research Source。

每个外部研究资产必须保存版本、来源、抓取时间、代码 Commit / Release、License 和 Citation Metadata。

## 34.12 Agent 角色逻辑隔离

Agent Control Plane 至少逻辑区分：

```text
Planner
Researcher
Executor/Coordinator
Judge/Evaluator
Optimizer
```

不得由同一个逻辑角色同时完成：

> 提方案 → 改规则 → 考试 → 批准自己上线。

最终 Gate 仍由 Frozen Contract + Deterministic Evidence 决定。

## 34.13 Production Data Retention / Privacy

生产反馈用于持续优化，但原始业务内容不得默认无限期保存。

必须定义：

- raw request retention；
- response retention；
- prompt / output redaction；
- PII / secret detection；
- telemetry-only mode；
- no-content-logging mode；
- dataset promotion approval。

从 Production Feedback 进入 Dataset 的任何数据必须重新经过 Source/Data Policy 与 Dataset Gate，不能自动把用户请求直接变成训练集。

## 34.14 Plugin Configuration Schema

Plugin Manifest 除 Capability 外，预留版本化 `config_schema`。

后续 UI 可以根据 Schema 动态生成 Runtime / Training / Provider 的高级参数页，避免每增加一个框架就修改核心前端。

UI 仍属于下一阶段设计，本节只冻结功能 Contract。

## 34.15 成果申报材料包与提交边界

Innovation & IP Workspace 除 Draft 外，还应能够形成：

```text
Software Copyright Filing Package
Patent Filing Package
Reproducibility / Evidence Package
Official-format Export Adapter
```

包括后续官方格式/XML/表单导出的适配能力。

但最终：

- 权利人；
- 作者/发明人；
- 法律声明；
- 保护范围；
- 正式提交；
- 数字签名；

必须由授权人员确认执行，平台不得自主完成不可逆法律行为。

## 34.16 本轮功能审计结论

经本轮逐项对照，前述主架构与本节补遗共同覆盖此前功能设计讨论的一级和关键二级能力。

后续若出现新的框架、模型、训练方法、数据工具、调度算法或研究工具，原则上应通过：

```text
Plugin / Adapter
+ Capability
+ Contract
+ Registry
+ Gate
```

扩展，而不新增第二套 Authority 或推翻核心领域模型。

从本节开始，功能层面进入 **Freeze Candidate**；下一阶段转入模块 Contract 拆分与 UI / UX / Human-AI Interaction 设计。

---

# 35. Retrieval & Index Plane

知识库、RAG、Agent Memory、Research Wiki、Code Wiki 和多模态检索不能只依赖单一向量数据库。平台新增横向 **Retrieval & Index Plane**，统一管理“如何索引、如何召回、如何融合、如何重排、如何评测”。

## 35.1 核心职责

```text
Raw / Parsed / Wiki / Graph / Dataset
                ↓
          Index Builder
                ↓
 ┌──────────────┼──────────────┐
 ▼              ▼              ▼
Dense Index   Sparse Index   Lexical Index
 ▼              ▼              ▼
Vector ANN    SPLADE/BGE-M3    BM25
 └──────────────┼──────────────┘
                ↓
          Hybrid Retrieval
                ↓
        Multi-stage Retrieval
                ↓
             Reranker
                ↓
       Evidence / Citation Layer
                ↓
        RAG / Agent / Search
```

## 35.2 Retrieval 不等于 Vector Search

平台至少支持：

- Dense Vector Retrieval；
- Sparse Vector Retrieval；
- BM25 / Lexical Search；
- Metadata / Structured Filter；
- Hybrid Search；
- Multi-vector / Multi-modal Retrieval；
- Late Interaction；
- Reranking；
- Graph Retrieval；
- Temporal / Freshness-aware Retrieval；
- Citation-aware Retrieval。

因此 Knowledge Plane 不绑定单一“向量库”。

## 35.3 Vector / Search Backend 通过 Adapter 接入

统一 `RetrievalBackendAdapter` / `VectorIndexAdapter`，首批候选可包括：

```text
pgvector
Qdrant
Milvus
Weaviate
Vespa
LanceDB
OpenSearch / Elasticsearch
FAISS
sqlite-vec / embedded engines
Future Backend
```

选择哪一个后端必须由真实 Benchmark 决定，而不是在总纲中永久押注某个产品。

评测至少包含：

- Recall@K；
- Precision@K；
- MRR；
- NDCG；
- Hit Rate；
- P50 / P95 / P99；
- QPS；
- Index Build Time；
- RAM / VRAM / Storage；
- Filter Performance；
- Update Latency；
- Multi-tenancy；
- Operational Complexity；
- Cost。

## 35.4 Hybrid Retrieval 为默认能力方向

对于知识库和 RAG，默认能力应优先支持：

```text
Dense Semantic
+
Sparse / BM25 Exact Match
+
Metadata Filter
+
Fusion
+
Reranker
```

而不是“只做 embedding 相似度”。

Fusion 可通过 Adapter 支持：

- RRF；
- Weighted RRF；
- Score Fusion；
- Learned Fusion；
- Future Fusion Strategy。

## 35.5 Multi-stage / Late Interaction

平台预留：

```text
Stage 1  cheap retrieval
Stage 2  refine / rerank
Stage 3  evidence validation
```

例如：

```text
BM25 + Dense
   ↓
Top 100
   ↓
ColBERT / Multi-vector / Cross Encoder
   ↓
Top 20
   ↓
Citation / Source / Freshness Gate
   ↓
Top 8 Evidence
```

Retriever 和 Reranker 都必须是可替换 Capability。

## 35.6 Embedding Model Registry

Embedding 不能只是一个配置字符串。

需要记录：

- model_id；
- revision；
- dimensions；
- modality；
- language；
- normalization；
- tokenizer；
- max_length；
- license；
- benchmark；
- cost；
- hardware profile；
- compatible index type。

更换 Embedding 模型通常意味着 Index Version 变化，不能静默覆盖旧向量。

## 35.7 Index Lifecycle

Index 也是一级派生资产：

```text
BUILDING
→ VALIDATING
→ READY
→ ACTIVE
→ REBUILDING
→ STALE
→ SUPERSEDED
→ RETIRED
```

每个 Index 必须引用：

```text
source_snapshot
embedding_model_revision
chunking_recipe
index_backend
index_parameters
build_time
quality_evidence
```

禁止“换 embedding 后沿用旧 index”这类不可追溯操作。

## 35.8 Query Planner

Retrieval Query Planner 根据查询类型自动选择：

```text
Exact keyword
→ BM25 / Sparse

Semantic
→ Dense

Mixed
→ Hybrid

Multi-modal
→ Multi-vector

Entity / Relation
→ Graph

Time-sensitive
→ Freshness-aware

High-precision
→ Hybrid + Reranker
```

Agent 可以提出查询计划，但最终执行由固定 Retrieval Contract 完成。

## 35.9 Retrieval Evaluation

每个知识库都应该拥有自己的 Retrieval Gold Set，而不是只评最终 LLM 回答。

至少拆分：

```text
Retrieval Quality
Rerank Quality
Context Quality
Answer Quality
Citation Quality
```

这样才能判断问题究竟来自：

- 没召回；
- 排错了；
- Chunk 不好；
- Embedding 不好；
- Reranker 不好；
- LLM 推理错误。

## 35.10 Knowledge Plane 与 Retrieval Plane 的关系

```text
Knowledge Plane
负责：
“知道什么、知识来自哪里、是否可信、是否过期”

Retrieval & Index Plane
负责：
“如何最快、最准地把正确证据找出来”
```

两者必须分离。

---

# 36. Decision Model / Fast Decision Capability

除生成式 LLM 外，平台预留一类面向软件自动化的 **Decision Model Capability**。

它不是传统文本生成，而是：

```text
State
+ Typed Question / Choice / Score
        ↓
Decision Model
        ↓
Typed Decision
+ Probability / Confidence
```

## 36.1 典型用途

适合：

- Router；
- Admission Decision；
- Agent next-step selection；
- Retry / Stop；
- Risk Scoring；
- Guardrail；
- Classification；
- Candidate Ranking；
- Human-escalation decision；
- Tool selection；
- Judge / Verification 辅助。

## 36.2 与 LLM 的关系

Decision Model 不替代 LLM。

建议：

```text
LLM
负责：
生成、推理、解释、代码、长文本

Decision Model
负责：
低延迟、结构化、概率化决策
```

未来同一 Workflow 可以组合：

```text
Fast Decision Model
→ 判断是否需要昂贵推理

if high confidence:
    deterministic path
else:
    call reasoning LLM
```

从而降低延迟与成本。

## 36.3 Jev 作为当前新技术候选

当前可将 TypeSafe AI 的 **Jev** 作为 Decision Model 类的一个 Candidate Provider，而不是写死成平台依赖。

通过：

```text
DecisionModelAdapter
├── JevProviderAdapter
├── LocalClassifierAdapter
├── LocalSmallModelAdapter
└── FutureDecisionModel
```

进入 Technology Radar / Reproduction / Benchmark / Gate。

重点评测：

- calibration；
- accuracy；
- confidence reliability；
- latency；
- cost；
- consistency；
- failure mode；
- privacy；
- provider availability。

平台不采信厂商宣传值作为 Gate 依据，必须在自己的任务集上复测。

## 36.4 与 Agent Control Plane 的结合

Agent 每一步不一定都调用大型推理模型。

可形成：

```text
Observe
  ↓
Fast Decision
  ├─ obvious → deterministic action
  ├─ uncertain → reasoning LLM
  └─ risky → Human Gate
```

这将成为 Agent 自动化的一个新的成本 / 延迟优化层。

---

# 37. Knowledge Retrieval 技术演进原则

Knowledge / Retrieval 领域变化很快，因此总纲冻结的是能力，不冻结具体产品。

未来出现新的：

- Vector Engine；
- Sparse Engine；
- Search Engine；
- Graph Engine；
- Embedding Model；
- Reranker；
- Late Interaction；
- Neural Index；
- Learned Retriever；
- Agent Memory Engine；

都遵循：

```text
Discover
→ Reproduce / Benchmark
→ Adapter
→ Candidate
→ Gate
→ Active
```

而不是修改 Knowledge Plane 或 Retrieval Plane 的核心 Authority。



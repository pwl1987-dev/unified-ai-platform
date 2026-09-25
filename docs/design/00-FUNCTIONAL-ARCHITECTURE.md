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
> 它要建设成一个 **模型无关、框架无关、厂商无关的 Unified AI Gateway + AI Control Hub**：统一承载 AI 算力、模型、数据、知识、搜索、记忆、工具、Agent、自动实验、生产服务和持续创新。

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

先不看具体产品名，可以理解为十六组能力：

| 能力域 | 解决的问题 |
|---|---|
| **Compute & Environment** | 算力在哪里、是否健康、如何隔离和分配 |
| **Model & Capability** | 有哪些模型/算法/专精能力、是否合格 |
| **AI Asset & Capability Hub** | 从哪里找模型/数据集/工具/工作流，如何获取、训练、评测、部署和复用 |
| **Data & Knowledge** | 数据从哪里来、质量如何、如何形成知识和训练集 |
| **Search & Retrieval** | 如何做全文、向量、稀疏、混合、图和多模态检索 |
| **Memory** | Agent、项目、运维和长期知识如何持续记忆与更新 |
| **Tool / MCP & Actions** | 模型和 Agent 可以安全调用哪些工具和外部能力 |
| **Browser / Computer Use** | 如何在隔离和审计下执行网页与桌面任务 |
| **Code Intelligence** | 如何搜索、理解、索引和分析代码仓库 |
| **Experiment & Training** | 如何训练、量化、复现、比较和优化 |
| **Serving & Gateway** | 如何把模型、工具、Agent 和检索能力统一提供给业务 |
| **Scheduler & Resource** | 业务与训练如何共享资源并自动弹性 |
| **Workflow / Event / Messaging** | 长任务、事件流、队列、重试和恢复如何可靠运行 |
| **Agent Automation** | 哪些复杂步骤由 Agent 自动规划和协调 |
| **Research & Innovation** | 如何吸收新技术、形成论文/专利/软著 |
| **Governance & Security** | 权限、预算、安全、Gate、审计和可追溯性 |

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

平台不以“模型品牌”为核心，而以 **Capability** 为核心；同时不要求所有 Capability 都必须由“大模型”实现。传统机器学习、小型专精网络、统计模型、规则系统、优化器和工业算法流水线均可作为一等能力接入。

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

---

# 38. Model / AI Capability Taxonomy

平台的能力分类不能等同于“LLM 分类”。统一抽象应为：

```text
Capability
  ↓
Implementation
  ├── Foundation Model
  ├── Small Specialized Model
  ├── Classical ML Model
  ├── Statistical Model
  ├── Rule / Expert System
  ├── Optimization / Solver
  └── Composite Pipeline
```

因此 Registry 层建议逐步从“只管理 Model”扩展为：

```text
Capability Registry
+ Model Registry
+ Algorithm / Engine Metadata
```

其中 `Model Registry` 管理权重型模型，`Capability Registry` 才是业务长期稳定接口。

## 38.1 Generative Foundation Models

包括：

- Text LLM；
- Reasoning Model；
- Code Model；
- VLM；
- Omni / Native Multimodal Model；
- Image Generation；
- Video Generation；
- Audio / Music Generation；
- TTS / Speech Generation；
- Vision-Language-Action 等未来基础模型。

这些模型通常参数量较大，但平台不以“参数越大越高级”为原则。

## 38.2 Decision / System-One Models

单独作为一级模型类型：

- Jev / System-One style typed decision；
- Local Jev-style model；
- Distilled Decision Model；
- Choice / Score / Probability Model；
- Router Model；
- Risk Scoring Model；
- Admission Decision Model；
- Tool Selection Model；
- Retry / Stop Model。

本地化实现可通过 `DecisionModelAdapter` 接入。

截至 2026-09，已经出现多种独立的本地 Jev-style 实现，例如：

- 直接利用本地小型 LLM 的 masked-logit / first-token probability；
- 通过 llama.cpp / SGLang 提供 Choice / Score / Noul；
- 将 Teacher 的软标签蒸馏到更小的 Encoder / Classifier；
- 独立开放权重的 Jev-style student model。

这些均应进入 Technology Radar 和本地 Benchmark，而不是默认依赖云端 Jev。

重点 Gate：

- Accuracy；
- Calibration / ECE；
- Brier Score；
- Confidence Reliability；
- Latency；
- Throughput；
- CPU / GPU Cost；
- Out-of-domain Behavior；
- Abstention / Human Escalation Quality。

## 38.3 Embedding / Representation Models

Embedding 单独作为模型类型，而不是 RAG 的一个参数。

至少支持：

- Text Embedding；
- Multilingual Embedding；
- Code Embedding；
- Image Embedding；
- Audio Embedding；
- Video Embedding；
- Multimodal Embedding；
- Sparse Embedding；
- Entity / Graph Embedding；
- Metric Learning / Siamese Embedding。

Embedding Model 必须有独立 Benchmark 和版本生命周期，因为它直接决定 Index Compatibility。

## 38.4 Reranker / Retrieval Models

一级类型包括：

- Cross-Encoder Reranker；
- Bi-Encoder Retriever；
- Sparse Neural Retriever；
- Late-Interaction / ColBERT-style Model；
- Multi-vector Retriever；
- Query Rewriter；
- Query / Document Expander；
- Relevance Classifier；
- Evidence Selector；
- Memory Reranker；
- Learned Fusion Model。

因此 Retrieval Pipeline 可以组合：

```text
Retriever
→ Candidate Fusion
→ Reranker
→ Evidence Selector
→ Context Builder
```

而不是把所有能力压进 Vector DB。

## 38.5 Judge / Verifier / Reward Models

与生成模型分开管理：

- Reward Model；
- Pairwise Preference Model；
- LLM Judge；
- Factuality Verifier；
- Groundedness Verifier；
- Citation Verifier；
- Safety Judge；
- Code Verifier；
- Math Verifier；
- Hallucination Detector；
- Policy Compliance Model。

Judge 只能形成 Evidence / Proposal，不能单独拥有 Release Authority。

## 38.6 Classification Models

包括传统和深度分类：

- Text Classification；
- Image Classification；
- Audio Classification；
- Video Classification；
- Multi-label Classification；
- Intent Classification；
- Sentiment / Topic；
- Quality Classification；
- Defect Category；
- Alarm / Fault Category；
- Spam / Fraud / Risk Classification。

分类器可以从几十 KB 到数十亿参数，平台按 Capability 而不是参数规模统一管理。

## 38.7 Industrial Vision / Machine Vision

工业视觉是独立重点能力域。

至少支持：

### Detection

- Object Detection；
- Open-vocabulary Detection；
- Small-object Detection；
- Oriented Bounding Box / Rotated Detection；
- Industrial Part / Defect Detection。

### Segmentation

- Semantic Segmentation；
- Instance Segmentation；
- Panoptic Segmentation；
- Interactive / Promptable Segmentation；
- Industrial Surface / Region Segmentation。

### Tracking / Identity

- Single / Multi-object Tracking；
- Re-identification；
- Trajectory Analysis；
- Counting；
- Line Crossing；
- Zone Intrusion。

### Geometry / Measurement

- Keypoint / Pose；
- Depth Estimation；
- Stereo；
- Optical Flow；
- 3D Detection；
- Point Cloud / LiDAR；
- Measurement / Metrology；
- Alignment / Registration。

### Industrial Inspection

- Visual Anomaly Detection；
- Surface Defect Detection；
- Few-shot / One-class Defect Detection；
- Foreign-object Detection；
- Assembly Verification；
- Missing-part Detection；
- Quality Inspection；
- OCR / Barcode / QR / Character Recognition。

工业异常检测需单独支持类似“只用正常样本训练”的模型；例如 PatchCore 一类方法会使用正常图像特征 memory bank，通过最近邻距离定位异常区域。citeturn332485search12

YOLO 类框架只是其中一个 Adapter。当前 Ultralytics 文档所覆盖的任务已经包括 Detection、Instance/Semantic Segmentation、Classification、Pose、OBB、Depth，并可在检测/分割/姿态/OBB 结果之上进行 Tracking，因此我们的 Capability Schema 也必须比“YOLO=目标检测”更宽。citeturn332485search0turn332485search4

## 38.8 Video Understanding / 镜头与事件模型

视频任务不能只理解为 VLM。

至少支持：

- Shot Boundary Detection / 镜头切分；
- Scene Boundary Detection；
- Scene Classification；
- Action Recognition；
- Temporal Action Localization；
- Event Detection；
- Highlight Detection；
- Video Summarization；
- Multi-object Tracking；
- Video Anomaly Detection；
- Crowd / Flow Analysis；
- Lip / Gesture / Behavior Recognition；
- Temporal Segmentation。

这类“小而专”的模型往往比通用 VLM 延迟更低、成本更低，也更容易形成稳定工业指标。

## 38.9 OCR / Document Intelligence Models

进一步拆分：

- Text Detection；
- Text Recognition；
- Layout Detection；
- Table Structure Recognition；
- Formula Recognition；
- Handwriting Recognition；
- Document Classification；
- Key Information Extraction；
- Document Relation Extraction；
- Reading Order；
- Signature / Stamp / Seal Detection；
- Document Quality / Tamper Detection。

VLM 可以作为补充，但不应默认替代专业 OCR / Layout 模型。

## 38.10 Speech / Audio Specialized Models

包括：

- VAD；
- Keyword Spotting；
- ASR；
- Speaker Diarization；
- Speaker Identification / Verification；
- Acoustic Event Detection；
- Audio Classification；
- Acoustic Anomaly Detection；
- Speech Enhancement；
- Noise Suppression；
- Source Separation；
- Voice Activity / Turn Detection；
- TTS；
- Voice Conversion。

例如很多 VAD、KWS、声纹和工业声学异常检测完全没必要调用大语言模型。

## 38.11 Time-Series / Sensor / Industrial Process Models

这是工业平台必须补齐的一类。

至少包括：

- Forecasting；
- Anomaly Detection；
- Change-point Detection；
- Fault Diagnosis；
- Remaining Useful Life / RUL；
- Predictive Maintenance；
- Soft Sensor；
- Process State Estimation；
- Multivariate Sensor Fusion；
- Root-cause Ranking；
- Energy / Load Forecast；
- Vibration Analysis；
- Thermal / Pressure / Current Pattern Analysis。

实现可能是：

```text
Small Transformer
TCN / RNN / CNN
AutoEncoder
Graph Neural Network
Isolation Forest
XGBoost
State-space Model
Statistical Model
```

而不是强制 LLM 化。

## 38.12 Classical Machine Learning

传统机器学习作为一等 Capability，不作为“旧技术”排除。

至少支持：

- Linear / Logistic Regression；
- SVM；
- kNN；
- Decision Tree；
- Random Forest；
- Gradient Boosting；
- XGBoost / LightGBM / CatBoost 类模型；
- Naive Bayes；
- PCA / ICA；
- Clustering；
- Isolation Forest；
- One-Class SVM；
- Gaussian Process；
- HMM；
- Probabilistic Models。

对于结构化数据、小样本、高解释性、毫秒级 CPU 推理场景，这些模型可能优于大模型。

## 38.13 Statistical / Signal Processing Models

工业 AI 中必须允许非神经网络算法成为 Capability：

- ARIMA / ETS；
- State-space；
- Kalman Filter；
- Particle Filter；
- FFT / Spectral Analysis；
- Wavelet；
- Change Detection；
- SPC / Control Chart；
- Signal Envelope / Feature Extraction；
- Correlation / Causal Statistics。

这些能力可与学习模型组成 Composite Pipeline。

## 38.14 Expert System / Rule / Fuzzy Logic

“传统人工智能”也应纳入：

- Rule Engine；
- Expert System；
- Decision Table；
- Fuzzy Logic；
- Knowledge-based Diagnosis；
- Constraint Rules；
- Policy Engine。

典型用法：

```text
ML Model
→ Probability

Expert Rule
→ Safety Constraint

LLM / Agent
→ Explanation

Deterministic Gate
→ Final Action
```

平台不应该为了“AI 化”而强行把成熟规则逻辑改造成 LLM。

## 38.15 Optimization / Operations Research / Control

这类在工业系统同样属于智能能力：

- Linear Programming；
- Integer / Mixed Integer Programming；
- Constraint Programming；
- Scheduling Solver；
- Vehicle / Route Optimization；
- Resource Optimization；
- Bayesian Optimization；
- Evolutionary Algorithm；
- Reinforcement Learning；
- Model Predictive Control；
- Control Policy；
- PID / Controller Tuning。

它们可以直接成为 Agent Tool，也可以作为 Scheduler / Production 的专用求解器。

## 38.16 Graph / Recommender / Ranking Models

包括：

- Graph Neural Network；
- Node Classification；
- Link Prediction；
- Graph Embedding；
- Fraud / Relation Detection；
- Recommender；
- CTR / CVR；
- Learning-to-Rank；
- Candidate Generation；
- Matching；
- Personalization。

这与 Knowledge Graph / Retrieval Plane 相互连接，但生命周期和 Benchmark 独立。

## 38.17 Scientific / Physics-aware Models

预留：

- Physics-Informed Neural Network；
- Surrogate Model；
- Emulator；
- Differentiable Simulation；
- Scientific Foundation Model；
- Molecule / Protein / Material Model；
- Weather / Geospatial Model；
- PDE / Field Prediction。

它们可能需要完全不同的输入、指标和 GPU Profile，因此必须通过 Capability Schema 解耦。

## 38.18 Security Specialized Models

Security & Trust Plane 可调用：

- Malware Classifier；
- Intrusion Detection；
- UEBA / Behavior Anomaly；
- Phishing / Spam；
- DLP / Sensitive-data Detector；
- Secret Detector；
- Prompt Injection Detector；
- Toxicity / Abuse Detector；
- Model / Data Poisoning Detector；
- Supply-chain Risk Classifier。

安全模型不得拥有“自动放行”最终 Authority，只提供信号给 Policy / Gate。

## 38.19 Edge / TinyML / CPU-first Models

平台不能假定所有模型都跑在 4090 上。

支持：

```text
GPU
CPU
NPU
iGPU
Edge GPU
Embedded Accelerator
Future Accelerator
```

需要管理：

- ONNX；
- TensorRT；
- OpenVINO；
- TFLite；
- CoreML；
- GGUF / llama.cpp；
- vendor-specific runtime；
- tiny / quantized artifacts。

适合：

- 摄像头边缘检测；
- 工业网关；
- KWS / VAD；
- 传感器异常检测；
- 本地分类；
- 低延迟控制前置判断。

## 38.20 Composite AI Pipeline

实际工业能力往往不是单模型：

```text
Camera
→ Detector
→ Tracker
→ OCR
→ Rule Engine
→ Small Classifier
→ LLM Explanation
→ Deterministic Gate
```

或者：

```text
Sensors
→ Signal Processing
→ Anomaly Model
→ Fault Classifier
→ Knowledge Base
→ Decision Model
→ Human / Control System
```

因此 Deployment Unit 和 Workflow DAG 必须允许：

> **Model + Algorithm + Rule + Tool + LLM**

共同组成一个 Capability。

## 38.21 模型分类元数据

每个可学习模型至少逐步记录：

```yaml
model_class: ...
task_family: ...
modality: ...
architecture_family: ...
parameter_count: ...
input_schema: ...
output_schema: ...
runtime_targets: ...
hardware_targets: ...
latency_class: ...
memory_profile: ...
trainable: ...
incremental_learning: ...
explainability: ...
calibration: ...
license: ...
safety_class: ...
benchmark_profile: ...
```

业务不直接依赖这些字段；Router、Scheduler、Gate 和 Registry 使用它们做选择。

## 38.22 统一原则

平台模型体系最终遵循：

> **不是“大模型优先”，而是“最合适能力优先”。**

选择模型/算法时综合考虑：

```text
Accuracy / Quality
Latency
Determinism
Calibration
Resource
Cost
Privacy
Explainability
Maintainability
Safety
```

如果一个 20MB 工业异常模型能够稳定解决问题，就不应因为平台拥有 27B/70B 模型而强行调用大模型。

---

# 39. Search & Retrieval Capability Domain

平台不仅提供“模型推理”，还应提供统一搜索能力。

支持：

- Full-text Search；
- BM25；
- Dense Retrieval；
- Sparse Retrieval；
- Hybrid Retrieval；
- Metadata Filter；
- Multi-vector Retrieval；
- Multi-modal Retrieval；
- Graph Retrieval；
- Code Search；
- Web Search Adapter；
- Dataset Search；
- Model Search；
- Experiment Search；
- Log / Trace Search；
- Research / Paper Search。

统一抽象：

```text
SearchRequest
  ↓
Query Planner
  ↓
Search / Retrieval Backends
  ↓
Fusion / Rerank
  ↓
Evidence
```

Search 与 Retrieval 是平台的基础服务，可被：

- RAG；
- Agent；
- Research；
- Code Intelligence；
- Security；
- Operations；
- Dataset Factory；

共同复用。

---

# 40. GraphRAG & Knowledge Graph Capability

GraphRAG 不应只是某一个开源项目的名字，而应作为 Knowledge Plane 的一级检索模式。

统一能力：

```text
Source
→ Entity / Relation Extraction
→ Knowledge Graph
→ Community / Cluster
→ Summary / Synthesis
→ Graph Query
→ Evidence
→ LLM / Agent
```

平台支持：

- Entity Graph；
- Relation Graph；
- Event Graph；
- Temporal Graph；
- Citation Graph；
- Research Graph；
- Code Dependency Graph；
- Infrastructure Topology Graph；
- Experiment Lineage Graph。

GraphRAG 可与传统 RAG 组合：

```text
Vector Retrieval
+ BM25
+ Knowledge Graph
+ Metadata
+ Reranker
→ Context
```

GraphRAG Backend 通过 Adapter 接入，核心只掌握：

- Graph Schema；
- Provenance；
- Version；
- Evidence；
- Query Contract；
- Gate。

---

# 41. Memory Plane

长期记忆是独立一级能力，不应等同于“把聊天记录存数据库”。

平台将 Memory 至少拆成：

```text
Working Memory
Short-term Session Memory
Episodic Memory
Semantic Memory
Procedural Memory
Project Memory
Agent Memory
Operational Memory
Human-reviewed Memory
```

## 41.1 Agent Memory

Agent Memory 至少记录：

- Goal；
- Plan；
- Decision；
- Tool Result；
- Failure；
- Recovery；
- Preference；
- Constraint；
- Learned Pattern；
- Unresolved Question；
- Evidence Reference。

Agent 不允许把任意自然语言内容直接升级为长期事实。

Memory 写入需要：

```text
Observation
→ Candidate Memory
→ Normalize
→ Source / Evidence
→ Conflict Check
→ Policy
→ Commit
```

## 41.2 Memory Retrieval

Memory Retrieval 可组合：

- Recency；
- Relevance；
- Importance；
- Entity；
- Time；
- Project；
- User / Tenant Scope；
- Confidence；
- Evidence；
- Embedding；
- Graph；
- Reranker。

## 41.3 Memory Lifecycle

```text
OBSERVED
→ CANDIDATE
→ VERIFIED
→ ACTIVE
→ UPDATED
→ CONFLICTED
→ SUPERSEDED
→ ARCHIVED
→ DELETED / TOMBSTONED
```

所有 Memory 必须有 Scope 和 Retention Policy。

---

# 42. Tool / MCP / Action Plane

模型能力和“行动能力”必须分离。

统一 Tool Registry 管理：

- MCP Server；
- Native Tool；
- REST / OpenAPI Tool；
- CLI Tool；
- Database Tool；
- Search Tool；
- Browser Tool；
- Code Tool；
- Scheduler Tool；
- Infrastructure Tool；
- Internal Business Tool；
- Agent-to-Agent Endpoint。

每个 Tool 至少记录：

```yaml
tool_id: ...
version: ...
protocol: ...
input_schema: ...
output_schema: ...
permissions: ...
network_scope: ...
secret_scope: ...
risk_class: ...
timeout: ...
idempotent: ...
reversible: ...
approval_policy: ...
audit_policy: ...
```

## 42.1 MCP 只是协议适配，不是 Authority

平台支持 MCP，但核心不能绑定某个协议版本。

统一：

```text
ToolAdapter
├── MCPAdapter
├── RESTAdapter
├── OpenAPIAdapter
├── CLIAdapter
├── NativeAdapter
└── FutureProtocolAdapter
```

MCP Server 进入：

```text
Discover
→ Inspect
→ Permission Review
→ Sandbox
→ Test
→ Tool Gate
→ Active
```

Tool 调用必须经过：

- Identity；
- RBAC；
- Policy；
- Secret Scope；
- Network Scope；
- Risk；
- Audit；
- Budget；
- Approval。

---

# 43. Browser / Computer Use Plane

浏览器和桌面操作属于高风险 Action Capability，应单独管理。

支持能力：

- Browser Navigation；
- Form Fill；
- Download / Upload；
- Structured Page Extraction；
- Accessibility-tree Interaction；
- Screenshot / Vision Interaction；
- Login Session；
- Multi-step Web Workflow；
- Desktop UI Automation；
- Remote Computer Use；
- VM / Sandbox Computer Use。

统一：

```text
Agent
→ Action Planner
→ Policy
→ Browser / Computer Runtime
→ Observation
→ Evidence
```

## 43.1 安全边界

Browser / Computer Use 默认：

- Sandbox；
- Egress Policy；
- Download Quarantine；
- Credential Isolation；
- Domain Allowlist / Denylist；
- Human Approval for high-risk action；
- Screenshot / Action Audit；
- Bounded Steps；
- Timeout；
- Kill Switch。

外部网页内容一律视为 **Untrusted Data**，不得因为网页中的文字而改变 Agent System Policy、Tool Permission 或 Gate。

---

# 44. Code Intelligence Plane

代码本身也是一级知识资产。

能力包括：

- Repository Discovery；
- Code Search；
- Symbol Search；
- Definition / Reference；
- Dependency Graph；
- Call Graph；
- AST / Semantic Index；
- Commit / Diff Search；
- Blame / History；
- Architecture Extraction；
- Code Wiki；
- Vulnerability Search；
- Test Mapping；
- Code Ownership；
- Impact Analysis。

统一：

```text
Repo
→ Parse / Index
→ Symbol / AST / Embedding / Graph
→ Code Search
→ Agent
→ Evidence
```

Code Intelligence 服务于：

- Coding Agent；
- Security Agent；
- Research Agent；
- Refactor Agent；
- Release Gate；
- Documentation；
- Platform Self-Evolution。

代码搜索后端同样通过 Adapter 接入，平台不锁定某一搜索产品。

---

# 45. Event / Streaming Plane

平台不能只靠同步 API 和数据库轮询。

统一 Event Backbone 用于：

- Model lifecycle events；
- Dataset events；
- Experiment events；
- GPU health；
- Scheduler events；
- Deployment events；
- Security events；
- Audit events；
- Agent events；
- Research events；
- Knowledge update events；
- Production telemetry。

事件格式至少包含：

```yaml
event_id: ...
event_type: ...
source: ...
subject: ...
timestamp: ...
correlation_id: ...
causation_id: ...
tenant: ...
payload_schema: ...
payload: ...
```

支持：

- Pub/Sub；
- Stream；
- Consumer Group；
- Replay；
- Retention；
- Dead-letter；
- Ordering where required；
- At-least-once；
- Idempotent Consumer。

---

# 46. Messaging & Queue Plane

Event Stream 和 Job Queue 不是一回事。

平台需要统一 Messaging Adapter：

```text
MessagingAdapter
├── NATS / JetStream
├── Kafka
├── Redis Streams
├── RabbitMQ
└── Future Backend
```

用途包括：

- Async Job；
- GPU Job Dispatch；
- Data Pipeline；
- Training Workflow；
- Notification；
- Agent Task；
- Event Fan-out；
- Backpressure；
- Retry；
- Dead-letter；
- Delayed / Scheduled Work。

核心平台掌握：

- Message Contract；
- Job State；
- Idempotency；
- Lease；
- Retry Policy；
- Dead-letter Policy；

而不是依赖某个消息产品来定义业务状态。

---

# 47. Durable Workflow Plane

Agent 编排和消息队列之上，还必须有 Durable Workflow。

它负责：

```text
Long-running Workflow
Checkpoint
Retry
Resume
Compensation
Human Approval
Timeout
Parallel Step
Fan-out / Fan-in
Conditional Branch
Event Wait
State Recovery
```

典型流程：

```text
Download Model
→ Scan
→ Build Environment
→ Smoke
→ Benchmark
→ Gate
→ Deploy
```

即使 Controller / Agent / VM 重启，也必须能够从 Durable State 继续，而不是重新从第一步开始。

Agent 负责“决定下一步”，Workflow Engine 负责“保证这一步可靠执行”。

---

# 48. Model / Artifact Intake Factory

“找到一个模型 → 人工下载 → 人工试一下”正式升级为自动化流水线。

统一：

```text
Model / Artifact Discovery
→ Metadata Fetch
→ License / Usage Policy
→ Revision Pin
→ Manifest
→ Download
→ Hash
→ Signature / Provenance
→ Static Scan
→ Quarantine
→ Format Inspect
→ Runtime Compatibility Probe
→ Smoke
→ Benchmark
→ Gate
→ Registry
→ Candidate Deployment
```

## 48.1 Model Source Adapter

支持：

- Hugging Face Hub；
- ModelScope；
- GitHub Release；
- Vendor Model Hub；
- Internal Artifact Store；
- HTTP / Object Storage；
- Offline Import；
- Future Model Registry。

下载必须 pin：

- model_id；
- revision / commit；
- file list；
- hash；
- size；
- license；
- source URL / repository；
- downloaded_at。

## 48.2 自动权重测试

自动检测：

- format；
- architecture；
- tokenizer；
- config；
- dtype；
- quantization；
- custom code；
- runtime support；
- hardware requirements；
- VRAM estimate；
- context length；
- multimodal assets。

然后自动尝试候选 Runtime：

```text
Candidate Model
   ↓
Runtime Probe Matrix
   ├─ SGLang
   ├─ vLLM
   ├─ llama.cpp
   ├─ TensorRT / ONNX / OpenVINO
   └─ Specialized Runtime
```

支持的 Runtime 才进入 Benchmark。

## 48.3 自动 Benchmark 与模型画像

模型进入平台后自动形成：

```text
Capability Profile
Quality Profile
Latency Profile
Throughput Profile
VRAM Profile
Power Profile
Cost Profile
Safety Profile
Runtime Compatibility Profile
```

最终 Router 和 Scheduler 不看“模型名好不好听”，只使用 Profile + Policy 做选择。

---

# 49. AI Gateway / Control Hub 定位升级

平台最终北向入口不仅是 LLM Gateway。

目标演进为：

> **Unified AI Gateway + AI Control Hub**

统一纳管：

```text
Models
Providers
Capabilities
Tools
MCP
Agents
Search
Retrieval
Knowledge
Memory
Browser
Computer Use
Code Intelligence
Data Pipelines
Training
Experiments
GPU / Compute
Workflows
Events
Security
Research
Innovation
```

北向接口可以分为：

```text
AI Data Plane
├── Model API
├── Search API
├── Retrieval API
├── Tool API
├── Agent API
└── Workflow API

AI Control Plane
├── Registry
├── Policy
├── Scheduler
├── Gate
├── Observability
├── Security
└── Administration
```

业务系统最终依赖的是稳定 Capability，而不是底层具体实现。

---

# 50. Capability Intake Loop

以后遇到任何“底层能跑”的新技术，不直接硬编码到 Core，而进入统一 Intake：

```text
Discover
→ Classify
→ Acquire
→ Quarantine
→ Inspect
→ Reproduce
→ Benchmark
→ Security Gate
→ Capability Gate
→ Adapter
→ Candidate
→ Shadow / Canary
→ Active
```

适用对象不仅是模型，也包括：

- Model Weights；
- Runtime；
- Vector Engine；
- Search Engine；
- MCP Server；
- Tool；
- Browser Automation；
- Memory Engine；
- Graph Engine；
- Data Tool；
- Agent Framework；
- Scheduler；
- Compiler；
- Kernel；
- Quantizer；
- Training Framework；
- Evaluation Framework。

这保证平台“做大做强”的方式是：

> **不断吸收能力，而不是不断扩大 Core。**

Core 长期保持稳定：

```text
Authority
Policy
Registry
Scheduler
Gate
Lineage
Security
Audit
```

外围能力通过 Adapter 和 Capability Contract 持续增长。

---

# 51. AI Asset & Capability Hub

平台增加一级能力：**AI Asset & Capability Hub**。

它的定位类似“内部 Hugging Face / ModelScope”，但不是只做资产展示，而是把：

```text
发现
→ 获取
→ 验证
→ 训练
→ 评测
→ 优化
→ 部署
→ 使用
→ 导出
```

全部打通。

## 51.1 Hub 中可以找到什么

统一 Catalog 不只管理“大模型”。

至少包括：

### Models

- LLM；
- Reasoning；
- Code；
- VLM；
- ASR；
- TTS；
- OCR；
- Embedding；
- Reranker；
- Decision / Jev-style；
- Judge / Reward；
- Image / Video / Audio Generation；
- YOLO / Detection；
- Segmentation；
- Tracking；
- Anomaly Detection；
- Time-series；
- Classical ML；
- TinyML / Edge；
- Security Model；
- Scientific Model；
- Specialized Industrial Model。

### Datasets

- Text；
- Image；
- Audio；
- Video；
- Multimodal；
- Time-series；
- Sensor；
- Structured / Tabular；
- Graph；
- Code；
- Document；
- OCR；
- Industrial Inspection；
- Benchmark；
- Gold Set；
- Synthetic Dataset。

### Training / Optimization Assets

- Training Recipe；
- LoRA / Adapter；
- Fine-tune Config；
- Continued Pretraining Recipe；
- Quantization Recipe；
- Distillation Recipe；
- Calibration Dataset；
- Prompt / Template；
- Tokenizer；
- Optimizer Config；
- Scheduler Config。

### Runtime / Deployment Assets

- Runtime Profile；
- Container Image；
- Environment Profile；
- Deployment Template；
- GPU Resource Profile；
- Serving Profile；
- Autoscaling Profile；
- Edge Package。

### AI Application Assets

- Agent；
- MCP Server；
- Tool；
- Workflow；
- RAG Pipeline；
- GraphRAG Pipeline；
- Search Pipeline；
- Memory Backend；
- Code Intelligence Pipeline；
- Browser / Computer Automation；
- Demo / App。

### Evaluation Assets

- Benchmark Suite；
- Evaluation Dataset；
- Judge Model；
- Metric；
- Gate Profile；
- Regression Suite；
- Reproduction Contract。

因此 Hub 的资产单位不是“一个权重文件”，而是一个可追溯的 **AI Asset**。

## 51.2 Federated Catalog

平台自己的 Hub 不需要把所有外部资产重新人工录入。

通过 `HubSourceAdapter` 联邦发现：

```text
Internal Hub
├── Hugging Face
├── ModelScope
├── GitHub
├── Vendor Model Hub
├── Internal Artifact Store
├── Internal Dataset Store
├── Research Registry
└── Future Sources
```

用户可以从一个入口搜索：

```text
“中文 embedding”
“工业缺陷检测”
“video shot boundary”
“本地 reranker”
“Jev-style decision”
“ASR”
“金融时间序列”
```

返回结果时统一展示：

- Source；
- Task；
- Modality；
- Size；
- License；
- Runtime Compatibility；
- Hardware Requirement；
- Quality Evidence；
- Download Status；
- Trust / Security Status；
- Local Availability；
- Training Support；
- Serving Support。

## 51.3 外部资产与本地资产分层

Catalog 中资产至少区分：

```text
REMOTE_ONLY
DISCOVERED
MIRRORED
QUARANTINED
VERIFIED
LOCAL_AVAILABLE
TRAINABLE
SERVABLE
PRODUCTION_APPROVED
RETIRED
```

“搜索得到”不等于“允许生产使用”。

只有通过平台 Intake / Gate 的资产，才能成为本地可信 Capability。

## 51.4 一键获取，但不是盲目下载

用户选择一个外部模型后，平台自动：

```text
Resolve Source
→ Pin Revision
→ Check License
→ Check File Manifest
→ Estimate Size
→ Check Storage
→ Download
→ Hash
→ Provenance
→ Quarantine
→ Inspect
→ Runtime Probe
→ Benchmark
→ Register
```

支持：

- Full Download；
- Selective File Download；
- Resume；
- Local Mirror；
- Content-addressed Dedup；
- Shared Read-only Weights；
- Storage Tiering。

## 51.5 数据集也是一级资产

Dataset Hub 不是模型的附属页。

用户可以：

```text
Search Dataset
→ Preview
→ Inspect License
→ Profile
→ Sample
→ Download / Stream
→ Clean
→ Transform
→ Annotate
→ Version
→ Freeze
→ Train
```

训练集、验证集、测试集和 Benchmark-only 数据必须保持用途隔离。

Dataset Hub 与 Model Hub 通过 Lineage 关联：

```text
Model
  ↓ trained_on
Dataset Version
  ↓ derived_from
Source Snapshot
```

## 51.6 Training Factory

任何标记为 `TRAINABLE` 的模型可以进入统一训练入口。

```text
Choose Base Model
+ Choose Dataset
+ Choose Training Recipe
+ Choose Goal
+ Budget
        ↓
Training Planner
        ↓
Resource Admission
        ↓
Training / Fine-tune
        ↓
Evaluation
        ↓
Candidate Model
```

用户不必须先理解具体框架。

高级用户可以再展开：

- Framework；
- Optimizer；
- Learning Rate；
- Batch；
- LoRA Rank；
- Precision；
- Parallelism；
- Checkpoint；
- Scheduler。

## 51.7 Evaluation & Comparison

Hub 中的模型不能只展示“点赞、下载量和参数量”。

平台自己的核心排序依据应来自：

```text
Official Metadata
+ Community Metadata
+ Our Benchmark
+ Our Hardware Evidence
+ Our Production Evidence
```

支持：

- Compare Models；
- Compare Runtimes；
- Compare Quantizations；
- Compare Embeddings；
- Compare Rerankers；
- Compare Industrial Models；
- Compare Cost / Power / Latency。

对于本地环境，自己的 Evidence 优先于外部宣传指标。

## 51.8 One-click Use

通过验证的资产应支持多种“使用方式”：

### Online API

```text
Asset
→ Deploy
→ Capability Alias
→ Unified Gateway
```

### Batch

```text
Asset
→ Job
→ Scheduler
→ Output Artifact
```

### Workflow

```text
Asset
→ Pipeline Node
→ Workflow
```

### Agent Tool

```text
Asset
→ Capability / Tool
→ Agent
```

### SDK / Local

生成受控的 SDK / Client Config / Local Runtime Package。

业务用户只选择“能力”，不需要手工拼装底层组件。

## 51.9 Unified Output / Export Factory

“输出”不只是 API 返回文本。

平台应支持将经过验证的成果导出为：

- Unified API Endpoint；
- OpenAI-compatible Endpoint；
- Batch Result；
- Model Artifact；
- LoRA / Adapter；
- Safetensors；
- GGUF；
- ONNX；
- TensorRT Engine；
- OpenVINO Artifact；
- Edge Package；
- OCI Image；
- Deployment Bundle；
- Dataset Snapshot；
- Embedding Index；
- Knowledge Package；
- Benchmark Report；
- Reproducibility Package。

任何格式转换均生成新 Artifact Version，并保留 Lineage。

## 51.10 Internal Publish

内部训练或优化完成的模型可以“发布回 Hub”：

```text
Experiment
→ Candidate Artifact
→ Gate
→ Model Card / Capability Card
→ Internal Publish
→ Searchable
→ Reusable
```

自动生成的 Card 至少包含：

- 来源；
- 版本；
- Base Model；
- Dataset；
- Training Recipe；
- License；
- Runtime；
- Hardware；
- Benchmark；
- Known Limitations；
- Safety；
- Recommended Use；
- Gate Evidence。

这样同一个成果不会在不同项目里重复训练和重复踩坑。

## 51.11 Public / Private / Restricted

Hub 默认首先是组织内部平台。

资产可具有：

```text
PUBLIC
ORGANIZATION
PROJECT
PRIVATE
RESTRICTED
```

未来如果需要建设对外社区，可以在同一 Contract 上增加 Public Publishing，但不要求第一阶段就做社交社区。

## 51.12 Hub 与 Gateway 的关系

```text
AI Asset & Capability Hub
负责：
“有什么、从哪里来、能不能用、怎么训练、证据是什么”

Unified AI Gateway
负责：
“业务如何统一调用”

Scheduler / Runtime
负责：
“实际上在哪里跑、怎么分资源”

Governance
负责：
“谁能用、能用到什么程度”
```

最终形成：

```text
         Federated Sources
HF / ModelScope / GitHub / Internal / Vendor
                  ↓
          AI Asset Hub
                  ↓
      Acquire / Train / Evaluate
                  ↓
          Capability Registry
                  ↓
             Deployment
                  ↓
          Unified AI Gateway
                  ↓
     App / Agent / User / Workflow
```

---

# 52. Unified AI Marketplace View

在 UI 层未来可以把 Hub 呈现成统一的“AI 能力市场/目录”，但它首先是内部工程资产目录，而不是商业商城。

用户按任务找能力，而不是按品牌找模型：

```text
Text
Vision
Audio
Video
Embedding
Rerank
Decision
Search
Industrial AI
Time-series
Security
Scientific
Agent
Tool
Workflow
Dataset
```

每个条目统一支持：

```text
View
Compare
Acquire
Test
Train
Fine-tune
Evaluate
Deploy
Use
Export
Fork / Derive
Retire
```

这成为后续 UI / UX 的一个核心一级入口。

---

# 53. Open-Source Reuse & Commercialization Audit

平台优先采用“**稳定 Core + 成熟开源能力复用 + 自有 UI / Control Hub**”，避免从零重复开发已经成熟的基础能力。

本节记录当前第一轮开源复用与许可证审计结论。它是工程选型输入，不替代正式法律意见；任何准备打包发布、对外提供 SaaS、再分发或商业授权的版本，仍需在具体版本冻结后进行一次依赖级法律审查。

## 53.1 审计原则

不能只看组织名或主仓许可证。

必须至少逐项确认：

```text
Repository
+ Exact Revision
+ Root License
+ Subdirectory License
+ Optional Enterprise / EE Code
+ Direct Dependencies
+ Bundled Dependencies
+ Model Weight License
+ Dataset License
+ Runtime / Driver Terms
+ Redistribution Terms
```

核心规则：

> **软件许可证、模型权重许可证、数据集许可证必须分开审。**

不能因为 Framework 是 Apache-2.0，就默认其中下载的模型或数据也能商用。

## 53.2 第一批候选结论

### CSGHub / OpenCSG

适合作为 **AI Asset & Capability Hub** 的首选复用底座。

当前已核对：

```text
OpenCSGs/csghub              Apache-2.0
OpenCSGs/csghub-server       Apache-2.0
OpenCSGs/csghub-sdk          Apache-2.0
OpenCSGs/csghub-charts       Apache-2.0
OpenCSGs/csghub-omnibus      Apache-2.0
OpenCSGs/csghub-mcp-servers  Apache-2.0
OpenCSGs/llm-finetune        Apache-2.0
```

这些组件可进入优先二开候选池。

但是同一 OpenCSG 组织内存在不同许可证：

```text
OpenCSGs/csghub-dataflow     GPL-3.0
OpenCSGs/image-syncer        GPL-3.0
OpenCSGs/coagent             AGPL-3.0
OpenCSGs/csglite             Other / 待逐文件确认
OpenCSGs/csgclaw             Other / 待逐文件确认
```

因此禁止采用：

> “OpenCSG 组织项目全部自动批准”

这种粗粒度策略。

### CSGHub Dataflow 的处理

`csghub-dataflow` 当前为 GPL-3.0。

平台建议：

```text
默认：不嵌入 proprietary Core
可选：独立进程 / 独立部署 Adapter
上线前：单独 License Review
```

如果未来需要其能力，可优先：

1. 通过 API 以外部服务方式集成；
2. 或选择许可证更宽松的数据处理引擎；
3. 或自行实现符合我们 Contract 的 Data Worker。

### OpenCSG Coagent 的处理

`coagent` 当前为 AGPL-3.0。

由于它属于网络服务/Agent Framework 类，AGPL 对网络交互场景的源代码义务更敏感。

默认策略：

```text
REFERENCE_ONLY / OPTIONAL_EXTERNAL
```

不进入我们 proprietary / closed-distribution Core。

## 53.3 MLflow

`mlflow/mlflow` 当前主仓为 Apache-2.0。

适合复用：

- Experiment Tracking；
- Run / Metric；
- Artifact；
- Model Registry；
- Evaluation；
- Tracing；
- Evidence；
- GenAI / Agent Observability。

建议定位：

```text
Experiment / Evidence Backend
```

而不是平台 Authority。

我们的：

- Gate；
- Scheduler；
- Capability Registry；
- Production Promotion；
- Security Policy；

仍保留在自有 Core。

## 53.4 BentoML

`bentoml/BentoML` 当前主仓为 Apache-2.0。

`bentoml/OpenLLM` 当前也为 Apache-2.0。

适合：

- Generic Model Serving；
- Python Model Serving；
- Multi-model Pipeline；
- Container Build；
- CPU/GPU Specialized Model；
- Industrial AI；
- Embedding / Reranker；
- YOLO / OCR / Traditional ML；
- Job / API。

建议定位：

```text
Generic Serving Adapter
```

重要注意：

部分 BentoML 示例仓库（例如某些 BentoSentenceTransformers / BentoYolo 示例）当前未在仓库根部发现显式 LICENSE 文件。

因此：

> **示例代码不能因为“属于 BentoML GitHub 组织”就自动视为 Apache-2.0。**

没有明确许可证的示例：

```text
REFERENCE_ONLY
```

除非后续确认其许可证或自行重写实现。

同样，BentoML 能运行的模型权重仍需按模型自己的 License 审计。

## 53.5 LiteLLM

LiteLLM 是有价值的 Gateway Adapter 候选，但许可证边界比上述 Apache 项目复杂。

当前根 LICENSE 明确：

- `enterprise/` 之外代码：MIT；
- Enterprise 部分：单独 BerriAI Enterprise License；
- Enterprise License 对生产使用要求有效商业许可。

因此建议：

```text
LiteLLM OSS Core
→ 可作为 Provider / Gateway Adapter 候选

LiteLLM Enterprise Code / Commercial Features
→ 默认禁止进入我们的发行包
→ 除非单独采购 / 明确授权
```

另外社区已经公开提出过 OSS / Enterprise 功能边界不够物理清晰的问题。

因此 LiteLLM 风险等级建议：

```text
P1 / CONTROLLED_REUSE
```

而不是像 Apache-only 项目一样直接进入核心依赖。

如果采用，应：

- 固定 exact revision；
- 扫描 enterprise import；
- 禁止 vendoring enterprise code；
- SBOM 标记 MIT / commercial boundary；
- CI 自动检查 forbidden path；
- 仅将其视为 Gateway Adapter，不作为平台 Authority。

同时保留对其他 Gateway 候选（如 Bifrost / TensorZero 等）进行许可证与能力对照的空间。

## 53.6 ModelScope / ms-swift / FunASR

### ModelScope Core

`modelscope/modelscope` 当前为 Apache-2.0。

适合作为：

- Model Hub Adapter；
- Inference Pipeline Adapter；
- CV / Speech / Multimodal Model Intake；
- Dataset / Model Source。

### ms-swift

`modelscope/ms-swift` 当前为 Apache-2.0。

适合作为：

- SFT；
- LoRA / QLoRA；
- CPT；
- DPO / GRPO；
- Multimodal Fine-tuning；
- Quantization / Export；

等 Training Adapter 候选。

### FunASR

FunASR Toolkit 当前为 MIT。

但其官方文档明确：

> Toolkit License 与 Model Weight License 是两回事。

因此：

```text
FunASR Toolkit
→ MIT / 可作为 Adapter

FunASR / Third-party Weight
→ 必须逐模型卡、逐 revision 审核
```

部分权重可能采用独立的 Model License，而不是 MIT。

这进一步证明我们的 Hub 必须将：

```text
software_license
model_license
dataset_license
redistribution_policy
commercial_use_policy
```

分开建模。

## 53.7 初步复用等级

建议当前冻结为：

```text
P0 — 优先复用 / 二开
├── CSGHub Portal / Server / SDK
├── CSGHub Charts / Omnibus
├── MLflow
├── BentoML
├── ModelScope Core
└── ms-swift

P1 — 受控复用
├── LiteLLM OSS Core
├── FunASR Toolkit
└── OpenLLM

P2 — 可选独立服务 / 需特别审查
├── CSGHub Dataflow (GPL-3.0)
└── 其他 GPL 组件

RESTRICTED / 默认不进入 Core
├── OpenCSG Coagent (AGPL-3.0)
├── LiteLLM Enterprise
├── No-License 示例仓库
└── License=Other 且未完成审计的仓库
```

这里的 P0/P1/P2 表示“复用工程优先级与许可风险等级”，不是功能优劣排名。

## 53.8 SBOM / License Gate

所有进入生产镜像或发行包的第三方组件必须生成：

```text
SBOM
+ License Inventory
+ Copyright Notice
+ Source Revision
+ Dependency Graph
```

License Gate 至少输出：

```text
APPROVED
APPROVED_WITH_NOTICE
ISOLATE_AS_SERVICE
LEGAL_REVIEW_REQUIRED
REJECTED
```

禁止仅靠人工 Excel 长期维护。

License Scan 应进入：

```text
Capability Intake
Model Intake
Container Build
Release Gate
```

---

# 54. UI Ownership Strategy

UI 建议由我们自己设计和实现。

不是因为现有开源 UI 不能用，而是因为我们的产品边界已经显著超过 CSGHub / MLflow / LiteLLM 任一单项目。

## 54.1 为什么不长期 Fork CSGHub Portal 作为主 UI

CSGHub Portal 本身 Apache-2.0，可以合法作为参考或短期复用。

但它的产品 IA 主要围绕：

- Model；
- Dataset；
- Space；
- Code；
- Asset Hub。

我们的 UI 还必须统一表达：

- GPU / Compute；
- Runtime；
- Scheduler；
- Training；
- Experiment；
- Data Factory；
- Knowledge；
- Retrieval；
- Memory；
- Agent；
- Tool / MCP；
- Browser / Computer Use；
- Workflow；
- Security；
- Research；
- IP；
- Platform Evolution。

长期直接 Fork CSGHub Portal 会导致：

- IA 被上游产品结构绑死；
- 上游升级与自定义 UI 冲突；
- 权限模型出现双 Authority；
- 页面层需要大量反向改造；
- Control Hub 体验无法真正统一。

因此建议：

> **复用 CSGHub Server / SDK / OpenAPI，不把其 Portal 作为长期产品 Shell。**

## 54.2 UI 分层

建议：

```text
Our Web UI
        ↓
Our Control Hub API
        ↓
Adapter / Backend Services
├── CSGHub Server
├── MLflow
├── LiteLLM / Gateway
├── BentoML
├── Training Backend
├── Scheduler
├── Knowledge
└── Security
```

浏览器不直接同时调用十几个开源后端。

所有后端通过我们的 Control Hub API 聚合：

- Identity；
- Permission；
- Audit；
- Error Model；
- Resource ID；
- State；
- Human Approval。

这样 UI 永远只认识我们的领域模型。

## 54.3 开源 UI 的正确用法

现有开源 UI 可以：

- 作为功能参考；
- 用作开发/运维 fallback；
- 用于早期验证第三方服务；
- 借鉴交互模式；
- 合法情况下复用通用组件。

但正式产品 UI：

```text
Information Architecture
Navigation
Role View
Dashboard
Human Inbox
Workflow
Agent Interaction
Design System
```

全部由我们自己定义。

## 54.4 Headless-first

第三方系统优先选择：

```text
API-first
SDK-first
Headless-capable
```

UI 是否漂亮不是选型核心。

真正重要的是：

- API 完整；
- Contract 稳定；
- 权限可接管；
- 数据可迁移；
- 无强制 SaaS 依赖；
- 可以自托管；
- License 清晰。

---

# 55. Recommended Reuse Architecture v0

当前建议的复用结构：

```text
                    Our Unified AI Control Hub
       Authority / Policy / Gate / Security / Scheduler
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
    CSGHub               MLflow             Gateway
 Asset Backend       Experiment/Evidence   Adapter Layer
       │                   │                   │
       │                   │              LiteLLM OSS
       │                   │              / Alternatives
       │                   │
       ├───────────┬───────┴────────────┐
       ▼           ▼                    ▼
   BentoML     LLM Runtime         Training Adapters
 Generic       SGLang/vLLM        ms-swift / Custom
 Serving       llama.cpp
       │           │                    │
       └───────────┴──────────┬─────────┘
                              ▼
                        Compute Plane
                     GPU / CPU / NPU / Edge
```

其中：

### 我们自己掌握

```text
Unified Domain Model
Capability Registry Overlay
Authority
Policy
Scheduler
Gate
Security
Lineage
Human Approval
Platform Evolution
Unified UI
```

### 尽量复用

```text
Asset Storage / Hub
Experiment Tracking
Provider Compatibility
Generic Serving
Training Framework
Model Download
Model Source Adapter
Existing Runtime
```

这条边界是后续工程实施的重要冻结条件。

---

# 56. Upstream / Dependency Risk Governance

第三方依赖的主要风险不只来自技术变化，还来自许可证、商业策略、组织治理、人员、法律和供应链等人为因素。

平台必须把“上游是否仍值得依赖”作为持续治理对象，而不是一次性选型结论。

## 56.1 基本原则

> **Every external dependency must have an exit path.**

每一个关键外部依赖至少满足：

```text
Pinned Version
+ License Snapshot
+ Internal Mirror
+ Adapter Boundary
+ Owned Domain Model
+ Portable Data
+ Contract Tests
+ Replacement Plan
```

任何不满足上述条件、且会进入 Core Critical Path 的组件，不允许成为不可替代核心依赖。

## 56.2 许可证与商业模式漂移

需要持续监控：

- Open Source → Source Available；
- Permissive → Copyleft；
- Free Commercial Use → Commercial License；
- Community Feature → Enterprise-only；
- Dual License Policy Change；
- SaaS-only Feature；
- Redistribution Restriction；
- Managed-service Restriction；
- Trademark / Branding Restriction；
- New CLA / Contributor Terms。

历史上已经出现过类似变化：HashiCorp 在 2023 年将多个产品未来版本从 MPL 2.0 转向 BSL 1.1；Redis 在 2024 年经历从 BSD-3-Clause 到 RSALv2 / SSPLv1 的许可变化，之后 Redis 8 又增加 AGPLv3 选项。citeturn983177search8turn983177search5

对于已经按 Apache-2.0 获取的具体版本，Apache-2.0 本身明确授予 perpetual、worldwide、no-charge、royalty-free、irrevocable 的版权许可，因此上游未来改许可，并不会把那个已发布 Apache-2.0 版本“自动变成新许可证”；但新版本、补丁和后续功能可能不再沿用原许可。citeturn983177search0

所以平台必须保存：

```text
source_revision
release_date
license_text_hash
notice_snapshot
dependency_lock
artifact_hash
```

## 56.3 公司 / 组织层风险

需要关注：

- 公司被收购；
- 项目出售给另一家公司；
- 核心维护团队重组；
- 商业目标改变；
- VC / 收入压力导致 open-core 加速；
- 项目进入维护模式；
- 组织解散；
- 基金会治理变化；
- 社区版与企业版边界扩大。

这些变化不一定当天导致故障，但会显著改变未来维护和许可风险。

## 56.4 Key-person / Maintainer Risk

开源项目可能高度依赖少数维护者。

需要跟踪：

- Bus Factor；
- Core Maintainer 数量；
- Release Approver 数量；
- Commit Concentration；
- Maintainer Inactivity；
- 未处理 PR / Issue 增长；
- Release Cadence；
- Security Response Time。

如果一个关键依赖长期只由 1～2 人实际维护，应提高风险等级并提前准备替代路线。

## 56.5 Governance Capture / Community Fragmentation

需要防止：

- 项目治理被单一商业主体完全控制；
- Community Edition 持续缩水；
- 上游出现重大 Fork；
- 原项目与社区 Fork 分裂；
- 插件生态迁移到另一分支；
- API / SDK 社区实际停止跟随官方版本。

出现 Fork 时，平台应比较：

```text
Upstream A
vs
Community Fork B
```

而不是天然继续跟随原厂。

## 56.6 Technical Rewrite / API Break Risk

上游可能：

- 大版本推倒重写；
- 删除旧 API；
- 更换数据库；
- 更换插件协议；
- 改变存储格式；
- 重写权限体系；
- 重构部署模型；
- 强依赖 Kubernetes / SaaS。

任何升级都必须作为 Candidate：

```text
New Upstream Version
→ License Diff
→ SBOM Diff
→ API Contract Test
→ Data Migration Test
→ Security Test
→ Shadow
→ Gate
→ Promote / Reject
```

生产禁止自动跟随 `latest`。

## 56.7 Repository / Artifact Availability Risk

需要防止：

- GitHub 仓库删除；
- Release 删除；
- Tag 重写；
- Force Push；
- Container Image 被删；
- PyPI / npm 包撤回；
- Model Hub 权重撤回；
- Dataset 下架；
- CDN / 下载地址失效。

关键依赖必须保留：

```text
Internal Git Mirror
Internal OCI Mirror
Internal Package Mirror
Internal Model / Dataset Mirror
Content Hash
```

做到“上游消失，当前生产版本仍可构建和恢复”。

## 56.8 Supply-chain / Account Compromise

人为风险还包括维护者账号或发布链被攻击：

- Maintainer Account Takeover；
- Malicious Release；
- Dependency Confusion；
- Typosquatting；
- Compromised Package；
- Build Pipeline Compromise；
- Signing-key Compromise；
- Malicious Contributor。

因此新版本不能因为“来自官方仓库”就自动进入生产。

必须：

```text
Source Verification
→ Signature / Provenance
→ SBOM
→ Malware / Secret Scan
→ Dependency Diff
→ Quarantine
→ Reproduction
→ Gate
```

## 56.9 Model / Dataset Rights Risk

模型和数据比普通软件更复杂。

需要持续监控：

- Model License Change；
- Weight Takedown；
- Dataset License Change；
- Training-data Dispute；
- Copyright Claim；
- Privacy / PII Complaint；
- Commercial-use Restriction；
- Geographic Restriction；
- Derivative-model Restriction；
- Redistribution Restriction。

平台必须能够执行：

```text
License Revoked / Policy Changed
→ Identify Affected Assets
→ Lineage Impact Analysis
→ Stop New Deployment
→ Quarantine
→ Replacement / Retrain Plan
```

必要时追踪：

```text
Dataset
→ Training Run
→ Derived Model
→ Quantized Model
→ Deployment
```

完成影响传播。

## 56.10 Cloud / Provider Business Risk

即使 API 技术稳定，也可能发生：

- Price Increase；
- Free Tier Removal；
- Quota Reduction；
- Region Removal；
- Model Deprecation；
- API Sunset；
- Account Policy Change；
- Payment Requirement；
- ToS Change；
- Data-retention Policy Change；
- Provider Exit from Market。

因此外部 Provider 只作为可替换 Capacity / Capability Source。

业务永远调用我们的 Gateway，不允许直接把业务代码绑定到单一 Provider。

## 56.11 Security Support / EOL Risk

上游可能：

- 停止安全补丁；
- 结束 LTS；
- 停止某个 Python / CUDA / OS 版本；
- 不再修复 CVE；
- 新安全补丁只进入商业版。

Environment Registry 必须记录：

```text
supported_until
security_support
eol_date
replacement_candidate
```

达到 EOL 前提前触发迁移实验。

## 56.12 Trademark / Branding Risk

软件代码可用，不代表品牌可以自由使用。

UI、产品名称和对外宣传不得依赖第三方 Trademark 作为自己的品牌。

因此我们自己的：

- 产品名称；
- Logo；
- UI；
- Domain；
- API Namespace；

必须独立。

第三方名称仅作为“Backend / Integration / Adapter”展示。

## 56.13 Upstream Risk Registry

每个关键依赖建立持续风险记录：

```yaml
upstream:
  name: ...
  revision: ...
  license: ...
  license_hash: ...

ownership:
  organization: ...
  foundation_backed: ...
  bus_factor: ...

health:
  last_release: ...
  release_cadence: ...
  active_maintainers: ...
  security_response: ...

risk:
  license_drift: ...
  commercial_shift: ...
  abandonment: ...
  api_break: ...
  supply_chain: ...
  provider_lockin: ...

exit:
  replacement: ...
  internal_mirror: ...
  export_ready: ...
  migration_tested: ...
```

## 56.14 风险触发动作

建议风险状态：

```text
GREEN
YELLOW
ORANGE
RED
```

含义：

```text
GREEN
正常跟踪

YELLOW
出现治理 / 许可 / 维护趋势变化，停止无条件升级

ORANGE
启动替代方案验证，冻结重大新依赖

RED
停止升级 / 停止新部署，执行 Fork / Replace / Migrate
```

## 56.15 Upstream Independence Gate

任何关键第三方组件进入平台前，必须回答：

```text
如果它明天：
- 改许可证
- 被收购
- 停更
- 关闭仓库
- 删除镜像
- 涨价
- API 废弃
- 推倒重写
- 把功能移到 Enterprise

我们能否继续运行当前版本？
能否重新构建？
能否导出数据？
能否在合理成本内替换？
```

四项中任何关键答案为“不能”，则不能进入 Core Critical Path。

---

# 57. Dependency Sovereignty Principle

平台对第三方依赖的最终原则：

> **Use upstream capability, never surrender platform sovereignty.**

可以复用上游：

- 代码；
- Runtime；
- Model Hub；
- Training Framework；
- Serving Engine；
- Gateway；
- Search / Vector Engine；
- Workflow / Message Backend。

但必须始终自己掌握：

```text
Northbound Contract
Domain Model
Asset Metadata
Critical Data
Authority
Policy
Gate
Security
Lineage
Identity
Human Approval
Exit Path
```

这样，即使任何上游因人为或商业原因发生根本变化，影响范围也应被限制在：

```text
Adapter
+ Migration
```

而不是：

```text
Whole Platform Rewrite
```



# Qwen3.8-27B / RTX 4090 下一代推理栈测试总纲

> 适用仓库：`pwl1987-dev/unified-ai-platform`（MIG-01 迁移自 `pwl1987/qwen3.8-27b-8x4090-stack`，git history 连续）
> 制定基线：`main@f2d1054`（2026-09-17）
> 计划版本：v1.2（增加同规格设备跨机器复现门与第二轮深挖漏项）
> 主线：vLLM 0.29 + TP2 + Qwen3.8-27B coding-v1.1
> 目的：让不同 Agent 在当前服务器上按统一口径实测，并让另一台同规格设备仅依赖仓库与外部权重清单即可从零复现，最终形成可迁移的生产选型，而不是寻找一个脱离负载的“万能最快配置”。

## 0. 执行结论先行

本轮测试按以下优先级执行：

1. 先修正测试夹具与指标命名，再复现少量 vLLM 0.28 冻结基线，证明新测试环境与历史口径一致。
2. 认证 vLLM 0.29：target-only → DFlash2 → KVarN，任何一步不合格都不进入参数深挖。
3. 以 **2×RTX 4090 / TP2** 为交互式 Coding Agent、低延迟和长上下文主基线；保留 TP1 作为聚合吞吐对照。
4. 依次测试 native / FP8 / KVarN KV，DFlash2、MRV2、CUDA Graph、batch-sharded sampling、prefix cache。
5. 测试当前 W4A16、W4A8-FP8、FP8 W8A8、分层混合量化；NVFP4/MXFP4 仅作为兼容性/质量实验，不假定为 4090 原生 FP4 加速。
6. 四卡最终对比 `4×TP1`、`2×TP2`、`TP2+TP1+TP1`、`TP4`。
7. 用 Pi、Claude Code 等真实 Coding Agent 工作负载做最后裁决；所有 Agent 必须拉平模型、API、工具、Skills、MCP、任务、上下文和终止条件。
8. 通过功能、质量和性能门后，依次跑 2h、8h、24h 稳定性门。
9. 对最终 Profile 做同规格第二台设备 clean-room 复现；未通过不得标记为可迁移 Release。
10. 第三方 P2P/驱动修改最后单独测试；不得污染官方驱动基线或生产卡。

FastLLM 已停止作为当前候选；已有有效、无效和未完成证据继续保留，不删除、不重写，未来版本发生实质变化时再重开。

---

## 1. 已冻结事实与历史对照

以下数据已经存在于仓库，是新实验的回归锚点。它们分为“可直接比较的锚点”和“仅作方向性证据的资格结果”，不得混用测试口径重新解释：

| 指标 | 已认证结果 |
|---|---:|
| TP1 / MS1 / 32K / C1 生成速率 | 约 133.5 tok/s；历史短夹具输出为 193 token |
| TP1 / MS4 / 32K / C4 aggregate | 约 197.5–200 tok/s |
| TP2 / 32K / C1 生成速率 | 177.26 tok/s；历史短夹具输出为 262 token，不能与上一行视为严格 fixed-token A/B |
| TP2 / 32K / C4 aggregate | 约 149.6–155 tok/s |
| TP2 / 220K TTFT | 同夹具约 96.2–96.5s |
| TP1 / 220K TTFT | 同夹具约 147.2s；因此同口径加速约 1.53×，不是跨夹具的 1.93× |
| TP1 稳定上下文 | 224K；240K 仅边界档，KV 峰约 99.7% |
| TP2 稳定上下文 | 238K；形制上限 245760 |
| TP1 / TP2 长上下文 needle | 已有 5/5 通过证据；TP2 238K 目前只算单轮资格结果，不算 Release 稳定认证 |
| KVarN 对 native KV 的短上下文代价 | 约 -5.7% |
| 当前最优 DFlash2 | k=7；0.28 下 k=8 在 CG=8 时掉图且尾位零接受 |
| 当前 NBT | 2048；单卡 NBT=8192 已因 prefill 工作区 OOM 否决 |
| 当前热点 | Marlin 约占 GPU trace 83% |
| partial-tail prefix reuse | 4K prompt TTFT 约 -41% |
| 编译缓存 | 冷编译可能改变数值路径；当前证据支持冻结 cache 的必要性，但尚需“3 个独立冷 cache × 每个 2 次复用重启”完成确定性认证 |

### 1.1 `dig028-20260916` 审计限制

以下历史字段不得直接进入最终横评，必须在新夹具中修正：

- `bench_conc.py` 的 `decode_tok_s = completion_tokens / wall_s` 实际包含 TTFT，应重命名为 `e2e_output_tok_s`；真正的 decode 速率必须使用 decode 时间窗计算。
- `REPORT.md` 的 220K `1.93×` 来自跨夹具的 186.2s 与 96.2s；同夹具证据是 147.176s 与 96.468s，约 `1.53×`。
- 历史 TP1/TP2 短 D565 生成长度不同，不能单凭 133.5/177.26 宣称严格加速比；后续必须 fixed-token replay。
- `ngramgpu-verbatim.json` 中首行、末行检查均为 false，且格式/内容存在错误；其高输出速率只能算重复文本性能，不能算质量通过。
- 历史约 14W 的板卡功耗读数与负载不符，视为 GPU index/NVML 映射错误；该批结果不得计算 tok/J。
- 历史原始目录缺少逐实验 server log、patch/model/env 哈希与多 boot 证据的部分，只能作为研究证据，不能自动升级为 Release 证据。

权威证据：

- `eval/vllm/cuda13/dig028-20260916/REPORT.md`
- `eval/vllm/cuda13/dig028-20260916/PROD-SWITCH-TOPOLOGY.md`
- `eval/vllm/cuda13/usable-concurrency-20260916/REPORT.md`
- `eval/vllm/cuda13/usable-concurrency-20260916/SUMMARY.json`
- `docs/VLLM-OPTIMIZATION.md`

新 Agent 必须先读这些文件。不得把已经否决的 ngram_gpu、单卡 NBT=8192、未匹配 CUDA Graph 的 k=8 当作新发现重复消耗 GPU 时间。

---

## 2. 测试纪律

### 2.1 单变量原则

每个实验臂只改变一个主变量。以下任一项变化都必须生成新的实验 ID：

- vLLM 版本、commit、patch；
- target/drafter 权重或量化方式；
- TP/副本拓扑；
- KV dtype；
- DFlash2 方法、k、draft TP；
- `max_model_len`、`max_num_seqs`、NBT、CUDA Graph；
- prefix-cache 策略；
- 驱动、CUDA、PyTorch、NCCL；
- 功耗墙、GPU 卡位、compile cache；
- fixture、并发模型、到达率或输出长度。

不得一次升级版本、换量化、换 KV、换拓扑再与旧数字比较。

### 2.2 三层测试门

| 层级 | 用途 | 最少重复 |
|---|---|---:|
| Screen | 淘汰明显失败项 | 同一 boot 预热后 3 次，取中位数 |
| Qualify | 候选资格认证 | 3 个独立 boot；每 boot 3 次；固定并预热 compile cache |
| Release | 生产裁决 | 3 个独立 boot + 质量全门 + 2h/8h/24h 长稳 |
| Reproduce | 跨同规格设备复现 | 第二台机器从空环境部署；独立操作者；最终 Profile 全门复测 |

性能差异绝对值小于 3% 默认视为噪声，除非 95% 置信区间不跨 0 且重复 boot 一致。质量、安全、OOM、崩溃不适用 3% 容忍。

`Release` 只证明当前机器可生产；`Reproduce` 通过后才可称“同规格设备可迁移复现”。跨机器不要求逐位相同的性能数值，但要求相同质量结论、容量档位、Profile 排序和受控性能容差。

所有 A/B 必须同时满足：相同 fixture SHA、实际 input token、requested output token、停止条件、采样参数、cache 状态和客户端版本。任一项不同只能标记为非配对观察，不能计算正式加速比。

### 2.3 有效性状态

每个实验只能使用下列状态之一：

- `VALID_PASS`：配置与测量均有效，达到门槛；
- `VALID_FAIL`：配置与测量有效，但结果未达门槛；
- `INVALID`：夹具、环境、日志、缓存、功耗或测量口径错误，不得用于结论；
- `UNSUPPORTED`：当前软件/模型/硬件不支持；必须保存明确错误与能力探针；
- `ABORTED`：受外部任务、温度、生产占卡等影响中止；
- `REJECTED`：已完成验证并被质量、稳定性或收益门否决。

失败和无效数据都必须保留，不能只提交成功结果。

### 2.4 GPU 与生产隔离

当前目标设备按 4×RTX 4090 24GB 定义；仓库名称或历史记录不能代替现场硬件事实，可用卡数、卡位和占用仍必须以执行时预检为准。

- 不得假设 GPU 编号固定；按 GPU UUID 记录与分配。
- 不得停止、杀死或迁移未知进程。
- 现有 llama.cpp 生产 GPU、其他用户会话、训练和媒体任务默认不可动。
- 一个协调 Agent 负责 Git 写入；GPU 实验可以并行，但多个 Agent 不得同时修改同一工作树或同时 push `main`。
- `main` 是唯一开发分支；不创建临时/实验分支，不 force push、不 amend 已推送提交、不重写历史。

---

## 3. GitHub 落盘结构

本轮统一写入：

```text
eval/vllm/nextgen-20260917/
├── MASTER-TEST-PLAN.md              # 本文件，只按正式修订更新
├── STATUS.md                        # 当前 Phase、Last Completed、Current Task、Next Task
├── MANIFEST.yaml                    # 冻结硬件、模型、fixture、门槛与路径
├── METRICS-SCHEMA.md                # 指标定义、公式、时间窗与旧字段映射
├── REPRODUCIBILITY.md               # 从零部署、复现门、允许差异与故障排查
├── DECISIONS.md                     # 仅记录已由证据支持的选型结论
├── tools/                           # bootstrap、启动、探针、采集、汇总与校验脚本
├── fixtures/                        # 可公开/可复现的固定输入及 SHA256
├── repro/                           # 锁包、容器 digest、SBOM、补丁、硬件 schema 与复现命令
├── raw/
│   ├── valid/<experiment-id>/       # 原始 JSON/JSONL/Prometheus/NVML/NCCL/日志
│   ├── invalid/<experiment-id>/     # 无效证据及无效原因
│   └── unsupported/<experiment-id>/ # 能力探针与明确错误
└── reports/
    ├── phase-00-baseline.md
    ├── phase-01-vllm029.md
    ├── phase-02-tp2.md
    ├── phase-03-kv.md
    ├── phase-04-quant.md
    ├── phase-05-topology.md
    ├── phase-06-agent.md
    ├── phase-09-reproduction.md
    └── FINAL-RECOMMENDATION.md
```

`STATUS.md` 是本次实验战役的执行状态，不替代仓库已有 Roadmap/Authority。阶段完成后应把最终结论回写现有 `docs/VLLM-OPTIMIZATION.md` 或其明确继任文档，避免永久形成第二套项目状态体系。

实验 ID 格式：

```text
V29-T2-Q0-KVF8-SD7-MS1-NBT2048-C1-L032K-B01
│   │  │  │    │   │   │       │  │     └─ boot/run
│   │  │  │    │   │   │       │  └──── context
│   │  │  │    │   │   │       └─────── concurrency
│   │  │  │    │   │   └─────────────── scheduler token budget
│   │  │  │    │   └─────────────────── max_num_seqs profile
│   │  │  │    └─────────────────────── speculative decode
│   │  │  └──────────────────────────── KV profile
│   │  └─────────────────────────────── target quant profile
│   └────────────────────────────────── topology
└────────────────────────────────────── runtime
```

---

## 4. 每次运行必须采集的证据

### 4.1 环境与身份

每个实验目录必须包含 `manifest.json`，至少记录：

- 仓库 URL、Git SHA、working tree 状态；
- 日期、Agent 名称、实验 ID、状态；
- 主机名、内核、发行版、CPU、内存；
- `nvidia-smi -q`、GPU UUID、PCI bus、`nvidia-smi topo -m`；
- GPU board vendor/VBIOS、PCIe 当前与最大 Gen/width、BAR1、Resizable BAR、IOMMU/ACS、NUMA node；
- 主板/BIOS、CPU 型号与微码、RAM 容量/频率/NUMA、系统盘与文件系统；
- 驱动、CUDA runtime/toolkit、PyTorch、vLLM、FlashInfer、Triton、NCCL 版本；
- 容器 image digest 或 venv lockfile SHA256；
- apt/pip/conda 完整 lock、编译器/binutils/glibc、环境构建脚本与 SBOM；
- vLLM tag/commit、每个 patch 文件 SHA256；
- target、drafter、tokenizer、chat template 的文件清单 SHA256；
- 启动命令、完整非敏感环境变量、API 参数；
- `VLLM_CACHE_ROOT` 路径及 cache 冻结策略；
- fixture SHA256、随机种子、temperature、top-p、输出长度；
- 功耗墙、温度、P-state、空闲显存和后台 GPU 进程；
- persistence mode、application clocks/默认 clocks、CPU governor、IRQ/CPU affinity、ASPM 与 kernel cmdline；
- 开始/结束 UTC 时间。

模型、容器、编译缓存和 fixture 只要有一个无法确认身份，该轮标记 `INVALID`。

所有本机绝对路径必须通过配置项或仓库根目录推导；报告可记录解析后的路径，但启动/测试脚本不得硬编码 `/home/<user>`、特定盘符或逻辑 GPU index。模型与大型产物不入 Git，但必须提供稳定来源、相对放置约定、逐文件 SHA256 和离线校验命令。

### 4.2 性能指标

统一记录原始样本，不只记录平均值：

- 冷/热启动时间、API Ready 时间；
- TTFT P50/P95/P99；
- prefill tok/s；
- `e2e_output_tok_s = completion_tokens / (last_token_time - request_start)`；
- `decode_tok_s = (completion_tokens - 1) / (last_token_time - first_token_time)`，同时记录 TPOT P50/P95/P99；若只有一个输出 token则 decode 指标为 null；
- E2E latency；
- request/s、input tok/s、output tok/s、aggregate tok/s；
- 满足 SLO 的 goodput；
- 每请求排队时间、running/waiting 请求数；
- KV 占用峰值、cache usage、preemption、eviction；
- prefix hit tokens、命中率、partial-tail 命中；
- speculative accepted/proposed、总接受率、每位置接受率、tokens/step、ms/step；
- 每卡显存峰值、GPU/SM/显存控制器利用率、PCIe Tx/Rx；
- 功耗、温度、时钟、总能耗、tok/J；
- CPU、内存、磁盘 I/O；
- NCCL/all-reduce 时间占比；
- HTTP 状态码、超时、取消、重试、OOM、崩溃、JIT 编译和告警。

每个字段必须在 `METRICS-SCHEMA.md` 中定义单位、起止时间点、聚合方法和 null 语义。客户端 wall time、服务端 scheduler 时间和 profiler kernel 时间必须分栏，禁止都称为“decode”。历史兼容字段只能放在 `legacy_*` 命名空间。

### 4.3 测量链路自检

在 Phase 00 前先执行一次仪器校验：

- 客户端以单调时钟记录 request start、first byte、first token、每个 token、last token；保存原始时间戳而非只保存汇总值。
- 对 streaming 与 non-streaming 各跑一个已知短请求，确认 token 计数与服务端 usage 一致。
- 用 GPU UUID 将服务进程、NVML 采样、PCI bus 和输出文件绑定；禁止用可能被 `CUDA_VISIBLE_DEVICES` 重映射的逻辑 index 关联功耗。
- 空闲/预填/decode 三段功耗应符合物理常识；异常低值、恒定值或卡位不一致立即标记 `INVALID`。
- 记录采样周期、缺失样本、采样器自身退出码；tok/J 使用请求时间窗内总能量积分，不用平均功耗除以不匹配的速率。
- 在固定输出测试中验证 requested/completion token 数；EOS 提前停止的样本单列，不能与满长度样本混算。

### 4.4 正确性与质量指标

- 随机五针 exact match；
- 12-residue cold/warm/cross-boot/cross-replica 语义门；
- 输出垃圾、复读环、JSON/工具调用破坏、多轮约束丢失；
- `humaneval`、XFC/tool calling、GSM8K、IFEval 现有门禁；
- 仓库真实 coding tasks：测试通过率、功能正确率、回归数；
- 与冻结参考在 temp=0 下的逐 token 分歧位置；分歧必须人工/规则裁为 exact、benign、failure；
- FP8/KV/混合量化的 perplexity 或 NLL、输出任务质量与长上下文质量。
- verbatim/copy 夹具的逐行 exact、首尾行、顺序、编号格式、遗漏/重复/额外行；任何一项失败均不得以 tok/s 覆盖。
- fixed-token replay 的输出 token IDs、finish reason、输出 hash；target-only 与 speculative 的差异从首个 token 分歧处保存上下文。

质量门沿用仓库原则：任一轴绝对回退超过 2pp 即失败；代码/工具核心轴不得退步。对量化初筛可暂用 1pp 预警线，最终仍执行完整门禁。

---

## 5. 固定夹具与负载模型

### 5.1 微基准

| Fixture | 输入/输出 | 目的 |
|---|---|---|
| D565 | 约 565 prompt + 512 output | 延续 `ulmus_validate`，测纯 decode/DFlash2 |
| P4K | 4K prompt + 32 output | 短 prefill/TTFT |
| P32K | 32K prompt + 128/512 output | 常规长 prompt、C1/C2/C4/C8 |
| P128K | 128K prompt + 128 output | 最低可接受长上下文门 |
| P220K | 220K prompt + 128 output | 生产长上下文 |
| P238K | 238K prompt + 128 output | TP2 稳定边界复核 |
| P245K | 245760 max model len | 容量边界，不自动等于生产推荐 |
| P262K | 262144 max model len | 最终目标，只在前序门通过后测试 |

所有上下文长度必须记录“实际 tokenizer token 数”，不能用字符数或文件大小代替。

每个性能 fixture 同时提供两种冻结模式：

- `fixed-output`：禁用 EOS 或使用确定的 token replay，强制相同输出 token 数，承担严格 A/B；
- `natural-stop`：允许模型自然停止，承担真实任务体验与质量观察。

两种模式必须分开报告。D565 历史锚点继续保留，但新主比较以 fixed-output 版本为准；若不同配置产生不同 token IDs/finish reason，先判质量和可比性，再判速度。

### 5.2 长上下文正确性

每个长度使用 3 个 seed；每个 seed 在约 10/30/50/70/90% 位置埋入 5 个不可推断的随机键值。要求：

- 5/5 exact；
- 输出预算足以完整回答；
- 每次使用独立 cache salt，避免把 prefix hit 当作冷上下文能力；
- 保存实际 token 位置和模型回答；
- 至少一轮冷启动、一轮热启动、一轮重启后复测。

### 5.3 并发模型

同时测试两类：

1. Closed-loop：C1/C2/C4/C8，每个 worker 完成后立即发送下一请求，测极限吞吐。
2. Open-loop：Poisson 到达率从低负载逐级升至饱和点的 25/50/75/90/110%，测排队、P95/P99 和拒绝行为。

不得把“请求最终完成”误报为“真实 resident 并发”。必须同时报告 `max_running`、排队、preemption 与 KV 占用。

在 Phase 00 固定交互与批处理 SLO，例如 TTFT/TPOT/P95 上限；open-loop 的“goodput”只统计同时满足正确性、TTFT、TPOT 和错误率门的请求。若尚未确定生产 SLO，报告完整吞吐—延迟曲线，不得自行选择最有利阈值。

并发压力还必须覆盖：短/长请求同时到达、取消风暴、prefix 高命中/低命中、不同 sequence 长度导致的 head-of-line blocking，以及 GDN/Mamba 每序列状态随 C1/C2/C4/C8 的显存增长。

为定位非 GPU 瓶颈，至少增加一次分层测量：预先 tokenized 请求直达 backend、正常 HTTP/API 请求、经 router 请求。分别观察 tokenizer CPU、JSON 编解码、网络栈和路由开销；四副本压力下检查 32 核 CPU 与 30GB RAM 是否先于 GPU 饱和。

### 5.4 真实 Coding Agent 夹具

固定 12–20 个任务，覆盖：

- 仓库理解与定位；
- 小 bug 修复；
- 跨文件功能；
- 测试补齐；
- 重构且保持行为；
- API/契约修改；
- 文档与代码一致性；
- 长上下文下从 AGENTS.md、代码、测试、历史报告联合推理。

每个任务冻结仓库 commit、初始 dirty 状态、任务提示、允许工具、时间限制、最大轮数、测试命令和期望结果。可公开任务放 `fixtures/agent/`；涉及私密代码的任务只提交哈希、评分结果和脱敏摘要。

Agent 任务集必须分成开发集与从未用于调参的 held-out 裁决集，防止根据固定任务反复优化造成过拟合。量化校准集、阈值选择集和最终质量集也必须互斥并记录哈希。

---

## 6. Phase 00：预检与 0.28 基线校准

### 6.0 先通过 Harness Gate

在消耗正式 GPU 矩阵前，必须先完成：

1. 修正并发脚本字段：历史 `decode_tok_s` 改为 `e2e_output_tok_s`，新增真正的 decode/TPOT 计算。
2. 生成 `METRICS-SCHEMA.md`、JSON Schema 与最小单元测试，用合成时间戳验证公式。
3. 固定 TP1/TP2 完全相同的 input/output token 数、stop、seed 和采样参数。
4. 用 GPU UUID 完成功耗/温度/利用率关联自检，删除任何依赖逻辑 GPU index 的关联假设。
5. 每次运行自动保存 client raw events、server log、metrics snapshot、进程到 UUID 映射和退出码。
6. verbatim 夹具必须能故意检测出缺首行、缺末行、乱序、编号格式错误和复读。

Harness Gate 未通过，所有新性能数据标记 `INVALID`，不得进入 0.29 横评。

### 6.1 预检步骤

1. 只读记录 `git rev-parse HEAD`、`git status --porcelain=v1`、最近 commits。
2. 读取本文件第 1 节列出的历史报告。
3. 记录 `nvidia-smi`、GPU UUID、占用、温度、功耗、`nvidia-smi topo -m`。
4. 明确测试 GPU 池；未知/生产进程存在则换卡，不做 `pkill` 或容器全停。
5. 固定功耗墙。历史基准以 450W 为主；如要测试 250W，必须另建实验臂。
6. 校验 target/drafter/tokenizer SHA256 与已有 manifest 一致。
7. 固定 NTP/UTC、CPU governor、容器/venv、cache 目录。
8. 连续空闲 5 分钟后确认温度进入统一区间再启动。
9. 记录物理 GPU UUID 与 TP rank、服务 PID、NVML sampler 的双向映射，并以服务进程的实际显存占用做交叉验证。

### 6.2 只复现四个锚点

- TP1/MS1：D565 C1；历史方向性目标 133.5 tok/s 附近；另跑 fixed-output 512-token 新锚点。
- TP1/MS4：P32K C4；目标 aggregate 197.5–200 tok/s 附近。
- TP2：D565 C1；历史方向性目标 177.26 tok/s 附近；与 TP1 共用 fixed-output 512-token 新锚点。
- TP2：P220K C1；目标 TTFT 约 96.5s、needle 5/5；同夹具 TP1 约 147.2s，正式加速基准约 1.53×。

通过门：fixed-output 新锚点性能与冻结方向一致，P32K/P220K 同夹具中位数差不超过 5%，质量相同，无新 OOM/崩溃。历史 D565 由于输出长度不等只用于 sanity check，不单独阻断。未通过时先做环境 reconciliation，不得直接开始 0.29。

另做两个一次性证据补债：

- compile cache：3 个独立空冷 cache，每个完成首次编译后再做 2 次独立服务重启复用；比较输出 token IDs、kernel/runner 路径与性能分布。
- TP2 238K：3 boot × 3 seed 五针，保存 server log、metrics、实际 token 位置和 KV/状态显存；通过后才把“资格结果”升级为“稳定上下文锚点”。

产出：`reports/phase-00-baseline.md`、四个 raw 目录、环境 manifest。

---

## 7. Phase 01：vLLM 0.29 资格认证

0.29 的目标不是“版本号更新”，而是确认 MRV2、spec CUDA Graph、TP sampling、hybrid/Mamba prefix retention 等能力在本模型和 4090 上真实生效。

### 7.1 三层迁移

按顺序测试，上一层不通过不得进入下一层：

| 层 | 配置 | 必测项 |
|---|---|---|
| A | target-only + 当前 W4A16 + native KV + 32K | 启动、API、D565、P4K、质量 smoke、MRV2 日志 |
| B | A + DFlash2 recal drafter k=7 | 接受率、per-position、CUDA Graph、输出无损性、3 boot |
| C | B + KVarN overlay/backport | 224K/238K/245K、needle、prefix cache、显存、稳定性 |

每层同时保存：原生 0.29 tag/commit、最小补丁集、`patch --dry-run`、锁包、启动帮助输出和完整启动日志。补丁必须按功能拆分，不能把 0.28 大补丁盲目整包移植。

### 7.2 MRV2/Fallback 判定

- 从启动日志和运行时配置证明使用 MRV2；不能仅因“0.29 默认 MRV2”就认定。
- 若某功能触发 MRV1 fallback，标记该臂为独立运行时，不与 MRV2 性能混算。
- dual-batch overlap、custom logits processors 或投机方法若触发 fallback，先关闭该功能建立 MRV2 基线。
- 保存一次 `vllm serve --help` 和解析后的能力清单；不猜测不存在的 CLI 参数。

### 7.3 0.29 资格门

- target-only 质量与 0.28 相同；性能不回退超过 5%；
- DFlash2 输出无损门通过，接受率不得出现结构性崩塌；
- KVarN 长上下文至少恢复 128K，最终应达到 TP1 224K / TP2 238K 附近；
- 3 个固定 compile-cache boot 稳定；
- 无新 crash、OOM、prefix corruption；
- MRV2 与 fallback 路径被明确记录。

不通过时保留 0.28 为认证基线；不得为了使用 0.29 而降低上下文或质量门。

---

## 8. Phase 02：TP2 主基线深挖

### 8.1 固定起点

`0.29 + 当前 W4A16 + DFlash2 k=7 + TP2 + draft TP1 + 32K + native KV`。先在 native KV 上调度/算子优化，避免 KVarN 同时干扰；之后把胜出参数迁移到 FP8/KVarN。

### 8.2 实验矩阵

| 方向 | 候选值 | 怎么测 | 晋级条件 |
|---|---|---|---|
| draft TP | 1、2 | D565 C1/C2/C4；记录 draft 显存、accept、NCCL | C1/TPOT 或 C2 goodput ≥3%，质量不变 |
| batch-sharded sampling | OFF、ON | TP2，MS≥2，C2/C4/C8；确认模型实现 local logits | aggregate/goodput 提升 ≥3%；不支持则 `UNSUPPORTED` |
| max_num_seqs | 1、2、4、8 | D565 + P32K，分别跑 C1/C2/C4/C8 | 形成交互档和吞吐档，不强求单一值 |
| NBT | 1024、2048、3072、4096 | P4K/P32K/P128K；监控 FLA workspace OOM | TTFT/吞吐提升且不挤压稳定 KV 边界 |
| CUDA Graph | auto/现行、FULL padded；capture 8/16（按实际支持） | D565 C1/C4/C8；记录 graph/eager step | P95 TPOT 或 aggregate 提升 ≥3% |
| all-reduce | 0.29 默认、FlashInfer opt-out、auto/禁 custom AR | TP2 C1/C4，采集 NCCL/AR trace | 只保留真实使用路径和稳定胜者 |
| prefix retention | 0、合规周期、dense/None（若可用） | 真实 Agent 多轮 + partial-tail | warm/partial TTFT 改善，显存与冷路不退 |
| prefix match unit | 默认、32、64、128（须满足 block 约束） | 尾部改写 1/8/32/128 token | 命中更细且无错误/过高元数据成本 |
| admission control | queued reqs/tokens 多档 | open-loop P4K/P32K | 达到目标 P95 TTFT，503 可预测可重试 |

注意：0.29 的 batch-sharded sampling 要求 TP>1、`max_num_seqs>=TP`，且模型需实现 local logits。配置拒绝不是 bug；应保存能力探针并标记 `UNSUPPORTED`。

TP2 还必须做一次物理配对扫描：按 `nvidia-smi topo -m` 选择至少“最佳 PCIe/NUMA 邻接”和“最差可用配对”，运行 nccl-tests 与 D565/P32K。最终固定 GPU UUID 对；拓扑变化后历史 TP2 数字自动失效。记录 CPU affinity、NUMA node 和 tokenizer/client 所在 CPU，避免把 CPU/NUMA 差异误判为 TP 收益。

CUDA Graph 深挖不能只看启动日志：统计 capture 覆盖率、graph replay/eager step 比例、因 batch shape/context/spec verify 变化导致的 graph miss，并在长短混合负载中确认 FULL padded graph 没有以额外显存换来 OOM 或容量下降。

### 8.3 dynamic k / speculative 细化

1. target-only 建立无投机参考。
2. k=5/6/7；每档记录总接受率、每位置接受率、tokens/step、ms/step。
3. k=8 只做一次 0.29 能力复核：CUDA Graph 必须覆盖 verify batch，且先证明第 8 位有非零有效接受；否则立即关闭。
4. 若 0.29/补丁真实支持 dynamic k，比较 fixed k=7 与 dynamic；保存每请求实际 k 分布。
5. temperature=0、seed 固定，与 target-only 做 token diff；投机方法导致输出质量破坏即否决，不能用速度抵消。
6. acceptance 必须按中文、英文、代码、工具 JSON、verbatim、短/长 prompt 和多轮 Agent 分桶；总体均值不能掩盖某类任务的接受率崩塌。
7. 记录 drafter 自身时间、target verify 时间、调度空泡和额外显存，计算投机净收益；只看 accepted/proposed 不足以证明加速。

最终形成两个 TP2 Profile：

- `L2`：C1/C2 交互低延迟；
- `X2`：128K–262K 长上下文。

---

## 9. Phase 03：KV Cache 三路对决

主矩阵：

| KV Profile | 用途 | 必测说明 |
|---|---|---|
| Native BF16/FP16 | 质量与短上下文性能参考 | 32K/64K；不要求达到极限上下文 |
| FP8 E4M3 | 4090 正式候选 | 默认 scale=1.0 只能作为诊断；必须另做校准版本 |
| FP8 calibrated | 平衡候选 | per-tensor；后端支持时加 per-head；保存校准集与 recipe |
| KVarN K4V2 G128 | 极限容量候选 | 224K/238K/245K/262K，记录约 5.7% 历史性能税是否变化 |

### 9.1 每个 KV Profile 怎么测

1. D565 C1/C4：短上下文 decode 与 DFlash2 acceptance。
2. P4K/P32K：prefill、TTFT、partial-prefix。
3. P128K/P220K/P238K：TTFT、decode、显存、needle。
4. 达到容量候选后再测 P245K/P262K。
5. 3 seed 五针；完整质量门至少跑一次。
6. 记录每层/每 attention type 实际 KV dtype；不能只看全局参数。
7. FP8 默认 1.0 scale 与校准 scale 分开命名，禁止混算。
8. 若某些 full-attention/首尾层敏感，测试 `kv_cache_dtype_skip_layers` 的最小跳过集合；每次只增加一组。
9. 对 hybrid GDN/Mamba 模型分开记录 attention KV 与 recurrent state 的显存；检查状态在完成、取消、超时和副本故障后是否及时释放。
10. 增加 churn 负载：长短序列交替、不同 prefix 租户、持续创建/取消请求，观察 block fragmentation、eviction、preemption 与错误复用。
11. prefix cache 做租户隔离与哈希碰撞/错误复用测试：不同鉴权主体、相同前缀、近似前缀、salt 变化和跨副本迁移均不得读取不属于该请求的状态或内容。

### 9.2 KV 选型门

- 日常 128K/220K：优先质量不退、TTFT/吞吐好、至少 10% KV 余量；
- 238K/245K：KV 峰达到 95% 以上只能标记边界档；
- 262K：必须 3 boot、3 seed 五针、无 preemption、无 OOM，并保留安全余量；
- FP8/KVarN 任一质量轴回退 >2pp 立即失败；
- 若 FP8 与 KVarN 容量相同且 FP8 更快/更准，KVarN 只保留更长上下文档。

---

## 10. Phase 04：权重量化与分层混合量化

### 10.1 先做能力探针

对每个候选先回答四个问题：

1. checkpoint 能否由当前工具正确生成并重新加载；
2. vLLM 实际选择了哪个 kernel/backend；
3. 4090/SM89 是否真正使用硬件支持路径，还是 Marlin 解量化/软件模拟；
4. 对 Qwen3.8 的 GDN、embedding、lm_head、DFlash2 是否完整兼容。

只要 backend 与预期不符，就先标记 compatibility 结果，不进入大矩阵。

### 10.2 量化 Profile

| ID | 主体 | 敏感模块 | 定位 |
|---|---|---|---|
| Q0 | 当前 AutoRound W4A16 G128 | int8 embed/lm_head | 冻结基线 |
| Q1 | MLP W4 G128 | attention/GDN G64，首尾层 W8/FP8 | 平衡档 |
| Q2 | MLP W4 G128 | attention W8/FP8、GDN G64、head FP8/BF16 | 高质量档 |
| Q3 | W4A8-FP8（实际支持时） | 首尾/头按敏感度提高 | Ada 高并发候选 |
| Q4 | FP8 W8A8 | FP8 | TP2 native-FP8 质量/并发候选 |
| Q5 | NVFP4/MXFP4 checkpoint | 敏感模块 FP8 | 非原生 FP4 研究档 |

Q5 不得宣传为 4090 原生 NVFP4。若落到 Marlin W4A16 fallback，应按实际 kernel 命名；若只能使用 slow emulation，仅做正确性 smoke，不做生产性能结论。

### 10.3 Layer sensitivity map

分两阶段，避免凭经验拍脑袋指定精度：

#### A. 离线模块敏感度

- 用冻结校准集采集 BF16/高精度 teacher activation；teacher 可使用 4 卡或 CPU offload，不要求作为生产 serving 配置。
- 对每层的 attention `q/k/v/o`、GDN recurrent/input/output projection、MLP `gate/up/down`、embedding、lm_head 计算：重构 MSE、cosine、NLL/perplexity 增量、Hessian/activation 加权误差。
- 分开统计 16 个 full-attention 层与 48 个 GDN 层，禁止只给“第 N 层”而不记录模块类型。
- 生成 `layer-sensitivity.csv/json`，排序高敏模块。
- 校准/敏感度开发集不得与 held-out 质量裁决集、真实 Agent 裁决任务重叠；记录样本来源、license、去重结果和 SHA256。

#### B. 端到端回恢复实验

- 从 Q0 开始，每次只把一组高敏模块恢复为 G64/W8/FP8/BF16；
- 首轮按模块族分组，第二轮在胜出模块族内细到层；
- 每个候选跑短质量集、D565、P32K、P128K needle；
- 使用显存增量/质量恢复/性能损失计算 Pareto 前沿；
- 最终只对 Pareto 候选跑全质量门。

### 10.4 每个量化 Profile 的测试矩阵

- TP2：C1/C2/C4/C8；
- P4K/P32K/P128K/P220K；
- native/FP8/KVarN KV 至少选两路组合；
- DFlash2 acceptance 与 target-only；
- 完整质量门、真实 Coding Agent 门；
- 模型大小、每卡 VRAM、启动时间、tok/s、TTFT、tok/J。
- FP8 scale/混合量化同时在短校准分布之外验证长上下文、代码、中文和工具调用；检查 scale saturation、NaN/Inf、异常层和跨 boot 漂移。

量化产物必须提交 recipe、校准数据 manifest、工具版本、量化日志、模块 dtype 清单和 SHA256；模型权重本身继续按仓库规则不入 Git。

### 10.5 立即淘汰条件

- 无法稳定加载或静默回退到非预期 kernel；
- 任一核心质量轴退步 >2pp；
- 产生复读、乱码、工具 JSON 破坏；
- 相同显存下同时比 Q0 更慢且质量不更好；
- NVFP4/MXFP4 只有模拟开销、无质量或容量收益；
- W3/W2 只有容量收益但无法通过质量 smoke。W3/W2 放到所有一级候选完成后再测。

---

## 11. Phase 05：四卡拓扑赛

### 11.1 四个必须比较的拓扑

1. `4×TP1`：四个独立实例，sticky LB；聚合吞吐候选。
2. `2×TP2`：两个独立 TP2 实例；双 Coding Agent 低延迟候选。
3. `TP2+TP1+TP1`：TP2 服务交互/长上下文，两个 TP1 服务批处理/短请求；通用生产候选。
4. `TP4`：极端单会话/长上下文实验候选；不得预设获胜。

### 11.2 统一负载

| 场景 | 请求模型 | 重点指标 |
|---|---|---|
| 单 Agent | P32K/P128K/P220K，C1 | TTFT、TPOT、decode、功耗 |
| 双 Agent | 两个独立 P32K/P128K 会话 | 每会话 P95、aggregate、公平性 |
| 四 Agent | 四个独立 P32K 会话 | aggregate、tail latency、KV 隔离 |
| 批处理 | D565/P4K，C4/C8/C16 | 最大 goodput、tok/J |
| 混合 | 1×长上下文 + 3×短请求 | 长请求饿死、短请求 P95、路由正确性 |
| prefix-sticky | 同会话多轮 + 新会话 | cache hit、漂移、故障转移代价 |

### 11.3 路由要求

- 四副本/混合拓扑使用同一个路由器版本；
- 记录选择原因、队列长度、cache/sticky 命中和故障转移；
- 不允许把同一会话随机分发后再用低 prefix hit 责怪推理引擎；
- 比较“每会话延迟”和“系统 aggregate”两个维度；
- 所有拓扑统一总 GPU 数、功耗墙、模型与 KV profile。
- 四个拓扑统一客户端机位、路由器版本、tokenizer worker 数和 CPU affinity；同时报告 direct-to-backend 与 through-router，量化路由/API 开销。
- 记录整机总能量而非只求单卡平均；独立实例还需记录 CPU、RAM、模型副本加载和 page-cache 压力，防止 `4×TP1` 的共享主机瓶颈被漏掉。

### 11.4 最终判定

- `4×TP1` 竞争吞吐冠军；
- `2×TP2` 竞争双交互低延迟冠军；
- `TP2+TP1+TP1` 竞争默认通用生产拓扑；
- `TP4` 只有在 C1/长上下文相对 TP2 有稳定、显著收益且通过稳定门才保留。

TP4 若只提高理论 KV pool、但不改善真实 262K×1、128K×2、64K×4 等任务，则不得以“总 KV token 容量”获胜。

---

## 12. Phase 06：真实 Agent 公平横评

### 12.1 拉平条件

Pi、Claude Code 或其他 Agent 必须使用：

- 同一个 target 模型与同一个 endpoint profile；
- 等价 OpenAI/Anthropic adapter 语义；
- 同一 system prompt、AGENTS.md、仓库 commit、任务文本；
- 同一可用工具、Skills、MCP 和权限；
- 同一上下文预算、最大输出、最大轮数、超时；
- 同一测试命令和成功定义；
- 清空任务工作树并从同一快照恢复；
- 一次只允许一个 Agent 修改该任务副本。

如果某 Agent 原生需要不同协议，adapter 只做协议映射，不加入额外推理、摘要或工具选择逻辑。

### 12.2 每任务采集

- 是否完成、测试是否通过、人工审查是否接受；
- 首次有效行动时间、总墙钟；
- API 请求数、输入/输出/cache token；
- TTFT、生成速度、重试、超时；
- 工具调用数、失败调用、重复读取、无效搜索；
- 修改文件数、diff 大小、返工次数；
- 编译/测试运行次数及浪费；
- 质量评分：正确性、最小改动、可维护性、安全性；
- 单成功任务 token、时间、能耗；
- 失败原因分类：模型、Agent 策略、adapter、工具、环境、任务本身。

### 12.3 统计方法

- 每个 Agent 每类任务至少 3 个，重要任务重复 3 次；
- 报告成功率和成功条件下的 token/时间，不得只比较平均 token；
- 任务必须配对比较；
- 给出中位数、P95、bootstrap 95% CI；
- “省 token”只有在成功率/质量不下降时才成立；
- 单独报告 prefix cache 冷/暖两轮，评估真实多轮开发收益。
- 随机化 Agent/任务/Profile 的执行顺序，并保留配对任务 ID，避免热缓存、温度和学习/重试顺序偏差。
- 自动评分通过后抽取固定比例盲审；评分者不知道使用的 Agent、量化或拓扑 Profile。

最终回答四个问题：

1. 哪个 Agent 成功率最高；
2. 在同等成功质量下谁最省 token；
3. 谁的墙钟/交互延迟最低；
4. 哪种 vLLM/拓扑 Profile 最适合该 Agent。

---

## 13. Phase 07：API、兼容、安全和运维

### 13.1 API/功能

逐项测试：

- OpenAI chat/completions、responses（若栈支持）、models、health；
- Anthropic Messages adapter；
- streaming/non-streaming；
- tool calling、并行工具、结构化 JSON schema；
- 多轮对话、system/developer/user 角色；
- stop、max_tokens、Unicode/中文、超长输入错误；
- 客户端取消、断连、服务端超时；
- 429/503、排队上限、重试后幂等；
- 服务器重启、热 cache、冷 cache；
- 日志与 metrics 在高并发下可用且不泄露 prompt/密钥。

### 13.2 故障注入

- 停掉一个副本，验证 LB 摘除与在途请求行为；
- TP rank 进程异常，验证整体失败是否被正确发现；
- KV 接近满载，验证拒绝/排队而非 silent corruption；
- compile cache 缺失/损坏，验证重新编译与证据标记；
- 磁盘不足、metrics 暂时不可用、客户端断连；
- 重启后确认模型/hash/config 未漂移。
- 取消/超时/断连后确认 sequence、KV block、GDN/Mamba state 和 scheduler slot 均被释放；重复 1,000 次后不得持续增长。
- 路由器重启、后端 ready 早报/晚报、半开连接与重试风暴；确认不会形成重复执行或无限重试。

不得在生产卡或真实用户流量上做破坏性故障注入。

---

## 14. Phase 08：稳定性与耐久

### 14.1 负载混合

建议长稳流量：

- 40% P4K/D565 交互；
- 25% P32K 多轮 Agent；
- 20% P128K；
- 10% P220K；
- 5% tool/JSON/取消/重试；
- 每 30–60 分钟插入固定 canary 和五针抽检。

### 14.2 时长门

1. 30 分钟 smoke；
2. 2 小时资格门；
3. 8 小时生产候选门；
4. 24 小时仅对最终 1–2 个候选执行。

### 14.3 通过标准

- 0 crash、0 OOM、0进程失联、0 semantic FAIL；
- HTTP 非预期错误率 <0.1%；
- 无持续显存/主存泄漏；
- 后半程 P50/P95 与前半程漂移 <5%；
- 温度、时钟、功耗无不可解释降频；
- prefix cache、DFlash2 acceptance 无阶段性崩塌；
- canary/needle 全过；
- TP/NCCL 无超时或 silent hang；
- 日志、metrics、结果文件连续完整。
- 服务重启后 Profile、模型 hash、runner、kernel、compile cache 与 GPU UUID 配对未漂移；恢复时间和失败请求数有界。

任一真正语义错误立即失败；性能抖动先定位温度、后台进程、编译、cache 与 arrival pattern。

---

## 15. Phase 09：同规格设备跨机器复现

### 15.1 复现目标与边界

第二台设备应满足同一硬件等级：4×RTX 4090 24GB、同等 CPU/内存能力和可比较的 PCIe 拓扑；显卡厂牌、GPU UUID、磁盘路径与主机名允许不同。必须明确区分：

- **数值重复性**：同机同环境多次运行的波动；
- **环境复现性**：清空软件环境后在原机重新部署；
- **跨机可迁移性**：同规格另一台机器从仓库资料独立部署；
- **结论复现性**：关键 Profile 排序、质量与容量结论保持一致。

跨机复现的目标是后面三项，不声称不同 GPU 芯片、主板和温度条件下性能逐位相同。

### 15.2 Clean-room 复现包

仓库必须足以指导一个未参与首轮实验的 Agent/操作者完成部署，至少包含：

1. `REPRODUCIBILITY.md`：前置硬件、安装、模型放置、执行顺序、预期输出和故障排查。
2. `repro/hardware-schema.json` 与采集脚本：自动判断硬条件、允许差异和警告项。
3. 锁定容器 digest，或完全锁定的 venv/系统依赖构建脚本；仅写版本范围不合格。
4. 所有源码 commit、patch、target/drafter/tokenizer/chat-template/fixture SHA256。
5. 一条 bootstrap 命令、一条 preflight 命令和分 Profile 运行命令；全部支持仓库相对路径和显式 GPU UUID。
6. JSON Schema、指标单元测试、已知小样本及预期结果，先证明测试工具本身复现。
7. 外部大型产物的获取位置、license/访问要求、校验和与不可获取时的明确阻断信息。
8. SBOM、环境变量模板、端口规划、磁盘/RAM/VRAM 最低容量和预计运行时长。
9. 原始结果到报告的确定性生成命令；报告不得依赖手工复制数字。
10. 脱敏检查：包内不得包含密钥、cookie、私密 prompt、用户名或不可迁移绝对路径。

compile cache 不得从首台机器复制后冒充冷复现。第二台机器先用空 cache 自行编译，再按规定预热并冻结；同时保存冷编译证据与后续复用证据。

### 15.3 跨机最小复现矩阵

只复现已经入围的 Profile，不重跑全部淘汰矩阵：

| 对象 | 必测内容 |
|---|---|
| Harness | 合成时间戳单测、token 计数、UUID/NVML 功耗自检、verbatim 负例 |
| S1 / TP1 | fixed D565 C1、P32K C4、质量 smoke、30min 稳定 |
| L2 / TP2 | fixed D565 C1/C2、P32K、NCCL/PCIe、质量 smoke |
| X2 / TP2 | P128K/P220K、最终 KV Profile、3-seed 五针、容量余量 |
| M4 / 四卡 | 最终拓扑的单/双/四 Agent、混合负载、router 与整机能耗 |
| 最终量化 | 完整核心质量轴、DFlash2 acceptance 分桶、kernel/backend 证明 |
| Release | 2h 长稳；首选默认 Profile 再跑 8h，必要时 24h |

### 15.4 跨机通过标准

- 模型、补丁、fixture、启动配置和指标 schema 哈希完全一致；硬件差异全部在允许清单内。
- exact/semantic/needle/tool JSON 等质量门与首机结论一致，不能使用性能容差豁免质量失败。
- 上下文容量档位一致；如果少一个计划档位、发生新 preemption/OOM，复现失败。
- TTFT、decode、aggregate 的跨机中位数偏差原则上 ≤7%，P95/P99 偏差 ≤10%；超出时先按时钟、温度、PCIe、CPU/NUMA、驱动与 cache 解释。
- 即使单项数值在容差内，若 S1/L2/X2/M4 的胜负排序或最终推荐发生反转，也必须标记 `REPRODUCE_FAIL` 并重新分析。
- 2h 稳定门达到与首机相同的零语义错误、零 crash/OOM 标准。
- 由未参与初始调优的第二操作者仅依据文档完成；若需要口头补充隐藏步骤，文档门失败。

结果状态新增：`REPRODUCE_PASS`、`REPRODUCE_WARN`（数值超容差但结论未变且原因可解释）、`REPRODUCE_FAIL`。输出 `reports/phase-09-reproduction.md`，并把所有必要修正回写 bootstrap、manifest 和本计划。

### 15.5 环境扰动复核

在第二台机器完成主复现后，只对最终 Profile 做小规模鲁棒性扫描：

- 冷机、热机与稳态温度；默认功耗墙和生产功耗墙；
- PCIe link 是否意外降为较低 Gen/width；
- CPU governor/NUMA 正确与错误绑定的差异，用于形成诊断阈值；
- 驱动允许的补丁版本升级、容器重建和整机重启；
- page cache 冷/暖、模型首次加载、compile cache 冷/暖；
- 后台轻量 CPU/磁盘干扰，确定观测到何种指标时应将实验判为 `INVALID`。

这些扰动用于形成可诊断边界，不用于放宽正式基线。

---

## 16. Phase 10：第三方 P2P / 驱动实验线

该阶段默认关闭，需在官方驱动 0.29 最优结果冻结后才启动。

### 16.1 前置条件

- 单独维护窗口和可回滚系统快照；
- 明确驱动、内核模块、Secure Boot、CUDA/NCCL 兼容性；
- 不使用生产 GPU/服务；
- 保存官方驱动完整对照；
- 用户明确同意进入驱动级实验。

### 16.2 测试顺序

1. 官方驱动下 `p2pBandwidthLatencyTest`、`nvidia-smi topo -m`、nccl-tests；
2. 修改驱动后重复完全相同测试；
3. TP2 C1/C4、TP4 C1/C4/C8；
4. P32K/P128K/P220K TTFT/decode；
5. 2h → 8h → 24h；
6. 回滚官方驱动并验证生产栈恢复。

只有真实 serving 收益达到以下任一条件才值得继续维护：

- TP2/TP4 交互延迟稳定改善 ≥10%；
- 四卡 aggregate/goodput 改善 ≥15%；
- 原本不可用的 TP4 变成明确胜者；
- 且质量、稳定性、可恢复性全部通过。

只提高微基准带宽、不改善真实请求，不进入生产。

---

## 17. 决策门与最终交付

### Gate A：0.29 是否替代 0.28

必须同时满足：功能/质量全过、长上下文不退、关键 Profile 性能不退超过 5%、3 boot 可复现、2h 稳定门通过。否则 0.28 保留认证基线。

### Gate B：TP2 是否成为主基线

交互/长上下文以 TP2 为主；聚合吞吐继续以 TP1 为对照。两者不强行合并成一个配置。

### Gate C：KV 选型

至少产出：短上下文质量/极速档、128K–220K 日常档、238K–262K 极限档。可以是三种不同 KV Profile。

### Gate D：量化选型

在“质量、C1、C4/C8、prefill、显存、功耗”上形成 Pareto 前沿，最终保留 2–3 个 Profile，不按 bit 数单轴排序。

### Gate E：四卡生产拓扑

必须分别回答：吞吐冠军、单 Agent 冠军、双 Agent 冠军、混合生产冠军；不得只报一个 aggregate 数字。

### Gate F：Release

最终候选通过真实 Agent、公平横评、API/故障门、8h；默认 Profile 再过 24h。

### Gate G：Reproduce

最终 S1/L2/X2/M4 在第二台同规格设备通过 Phase 09 后，才允许在结论中使用“可复现部署”或“同规格设备可迁移”。只通过 Gate F 时应写“当前主机 Release 通过”。

最终 `reports/FINAL-RECOMMENDATION.md` 必须包含：

- 冻结版本/补丁/权重/配置/hash；
- 4 个推荐 Profile 及适用路由；
- 全矩阵摘要与原始证据链接；
- 被否决项及原因；
- 未解决风险与 Verification Debt；
- 回滚方式；
- 生产部署与 LB 建议。

推荐 Profile 的目标形态：

```text
S1  TP1 吞吐档       短 prompt / batch / C4-C8
L2  TP2 交互档       Coding Agent / C1-C2
X2  TP2 长上下文档   128K-262K
M4  四卡混合档       TP2 + TP1 + TP1（仅实测胜出后定案）
```

---

## 18. 每阶段的提交规范

每个 Phase 按以下顺序：

1. 只读 reconciliation；
2. 更新 `STATUS.md` 为执行中；
3. 运行实验；
4. 原始证据先落 `raw/`，再生成报告；
5. 检查敏感信息、绝对模型路径、token、cookie、密钥是否已脱敏；
6. 运行 JSON/YAML/脚本校验和最小复现；
7. 更新 `STATUS.md`、`DECISIONS.md`（只有形成正式结论时）；
8. 审查 `git diff --check`、文件范围和大文件；
9. 单阶段一个或少量逻辑提交，push `main`；
10. 重新读取远端 `main` HEAD 与 CI，再开始下一 Phase。

提交示例：

```text
eval(vllm): qualify 0.29 target and dflash2 on TP2
eval(vllm): compare native fp8 and kvarn KV profiles
eval(vllm): add four-GPU topology matrix
docs(vllm): finalize next-generation serving recommendation
```

禁止：把模型权重、compile cache、私密 prompt、密钥、完整用户代码、大型 profiler trace 直接提交 Git。大型证据保存摘要、哈希、采集脚本和外部存放说明。

---

## 19. 给执行 Agent 的启动提示词

```text
继续推进 pwl1987-dev/unified-ai-platform 的下一代 vLLM 测试。

先只读核对 live main、eval/vllm/nextgen-20260917/MASTER-TEST-PLAN.md、现有 0.28 权威报告、GPU/进程占用、模型与环境哈希。不得根据聊天记忆猜状态，不得停止未知或生产进程。

main 是唯一开发分支；不新建分支、不 force push、不重写历史。一个协调者负责 Git 写入；可并行使用空闲 GPU 跑互不干扰的实验，但所有实验必须使用独立端口、独立 VLLM_CACHE_ROOT、独立结果目录，并固定功耗、fixture 和模型身份。

从 STATUS.md 的 Current Task 继续。严格执行单变量、Screen/Qualify/Release 重复规则和 VALID_PASS/VALID_FAIL/INVALID/UNSUPPORTED/ABORTED/REJECTED 状态。失败、无效和负结果同样落盘，禁止只保留成功数字。

完成当前 Phase 的全部实验、复现、报告、状态更新、diff 审查和必要验证后，提交并 push main；再开始下一 Phase。只有生产资源冲突、Authority/Contract 冲突、驱动级风险需要用户授权，或同一问题两轮合理修复仍无法收敛时才停止。
```

---

## 20. 官方能力依据（执行时仍以锁定版本帮助和源码为准）

- vLLM 0.29 release：MRV2 默认、CUDA Graph memory profiling、batch-sharded sampling、spec decode padded FULL CUDA Graph、Mamba prefix retention 等。
  - <https://github.com/vllm-project/vllm/releases/tag/v0.29.0>
- vLLM 0.29 `serve` 参数：
  - <https://docs.vllm.ai/en/v0.29.0/cli/serve/>
- FP8 KV cache、校准 scale 与按层跳过：
  - <https://docs.vllm.ai/en/v0.29.0/features/quantization/quantized_kvcache/>
- FP8 W8A8：Ada/SM89 支持路径与量化方法：
  - <https://docs.vllm.ai/en/stable/features/quantization/llm_compressor/fp8/>

文档只能说明“理论上存在能力”；本仓库的结论必须来自固定硬件、模型、补丁和 fixture 的本机原始证据。

---

## 21. v1.2 漏项审计结论

相对初稿，v1.1 修正了原始数据口径；v1.2 又补齐跨机器复现与第二轮深挖项目：

| 风险 | v1.1/v1.2 处理 |
|---|---|
| TTFT 被混入 decode | 建立指标公式、schema 与原始 token 时间戳 |
| 不同输出长度直接算加速比 | fixed-output 与 natural-stop 分轨；固定 token replay |
| 跨夹具 220K 比较 | 冻结同夹具 1.53×，1.93× 标为不可用于正式比较 |
| 单轮 238K 被当稳定认证 | 增加 3 boot × 3 seed 五针补债 |
| compile-cache 证据不足 | 3 冷 cache × 每个 2 次复用重启 |
| 功耗映射错误 | UUID/PID/PCI bus 三方关联与能量积分自检 |
| 高 tok/s 掩盖 verbatim 失败 | 加逐行/首尾/顺序/格式质量硬门 |
| 四卡只看 GPU 数字 | 加 router、CPU/NUMA、RAM、整机能耗与 direct/backend 对照 |
| hybrid state 泄漏/碎片未测 | 加 GDN/Mamba state、取消释放与 churn 测试 |
| 量化/Agent 调参过拟合 | 开发/校准/held-out 数据隔离与盲审 |
| TP2 卡位差异 | 增加 PCIe/NUMA 配对扫描并冻结 UUID 对 |
| 只在原机可重跑 | 增加同规格第二台设备 clean-room 复现、独立操作者和 Gate G |
| 环境“版本相同”但二进制不同 | 增加 digest、lock、SBOM、编译链与逐文件 SHA256 |
| 本机路径/逻辑卡号不可迁移 | 强制仓库相对路径、配置化资源和 GPU UUID |
| compile cache 被跨机复制 | 第二台机器必须空 cache 自编译，再验证复用 |
| 跨机数值容差无定义 | 中位数 7%、P95/P99 10%，质量/容量/排序不可豁免 |
| CUDA Graph 只看“已启用” | 增加 capture 覆盖率、graph miss、eager fallback 与显存代价 |
| speculative 只看总接受率 | 按语言/代码/工具/长度分桶，并计算 drafter+verify 净收益 |
| API/CPU 瓶颈冒充 GPU 性能 | 增加预 tokenized/backend/API/router 分层测量 |
| prefix cache 跨租户风险 | 增加 salt、近似前缀、碰撞、跨副本与租户隔离测试 |
| FP8/混合量化短集正常但长任务异常 | 增加 scale saturation、NaN/Inf 与跨分布/跨 boot 检查 |

本计划已经覆盖当前已知的一阶关键方向：版本迁移、runner/fallback、spec decode、CUDA Graph、KV/混合状态、权重量化、长上下文、并发、prefix cache、四卡拓扑、真实 Agent、API/故障、稳定性、能效、跨同规格机器复现与 P2P。暂不新增与当前目标无关的 LoRA、训练、结构化稀疏、多节点或异构 GPU 测试；若未来生产需求变化，再通过正式修订加入，避免矩阵无边界膨胀。

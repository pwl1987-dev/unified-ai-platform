# Phase 01 报告 — KV 因果裁决 + vLLM 0.29 资格认证（nextgen-20260917）

- 计划：v1.2（评审收敛版）；harness 权威指针 = commit `80e7d15`（measurement contract）/ `899eb5a`（runner safety baseline，STATUS 勘误）
- 环境：vllm29-env = vllm **0.29.0 @ g98dff2a81**（官方 release commit 98dff2a81d…），torch 2.13.0+cu130，全树 SHA `45c5c919…`（打补丁前基准，补丁台账见 repro/env029/patched-files-ledger.json）
- GPU：TP1=GPU2（41a1986d）/ TP2=GPU3+4（5fa853cd+aab40825）；250W 墙冻结；本报告数据全程 thermal-ready 形制
- Gate 定义：repro/gates-phase01.yaml（P0 冻结）；状态四层分离（实验六态 / reason / candidate_decision / Gate）

## §0 结论速览

| 项 | 结果 |
|---|---|
| **P1 KV 因果裁决** | **D2 归因推翻**：≥220K needle 失败与 KV dtype 无因果（2×2 四臂全 2/5，bf16/kvarn 输出逐字节同）；与长度无关（seed1@128K 同败）；为**码集（夹具内容）依赖**（seed99/seed2 全中）。≥200K 质量冻结令解除；needle 协议=多 seed + seed99 阳性对照 |
| P1.2 矩阵（Qualify） | kvarn/bf16 同分布镜像 9/9 格（3 真 boot）；seed99 6/6 全中；TTFT ref：kvarn 96.645s / bf16 104.219s（bf16 +7.8%） |
| fp8-KV | 0.28 栈 **UNSUPPORTED**（flashinfer CCCL JIT 双后端皆死）；FP8_DIAGNOSTIC 顺延 0.29——0.29 上 bf16 已可容，fp8 不再必要 |
| **P2 Layer A** | **PASS**（TP1 Qualify 3-boot +0.043%；TP2 资格 +0.026%；verbatim 100/100×3；MRV2 实证） |
| **P3 Layer B** | **PASS**（Qualify 145.008 vs 145.012 = +0.003%；**四通路跨版本同 hash `0bd1ecd6…` 逐位无损**；接受率 33.11→33.43%；unit-c 实证必移并移植） |
| **P4 Layer X bridge** | **PASS**（0.29 bf16+spec@220K：容量 1.42×、needle 三态等价、TTFT −0.09% vs 同 KV 参照）——0.29 长上下文资格 profile |
| **P4 Layer C KVarN port** | **STOP-LOSS**（4/6 尝试；布局契约 0.28-flat vs 0.29-padded-4D 非重排可解，正解=内核寻址重写=侵入 core 红线） |
| **Gate A-S**（预判） | 性能 ≤3% 高度一致档 ×3 形制；质量全同；MRV2 实证——2h 门后终判 |
| **Gate A-X** | 候选 = Layer X（bf16 eligible）；终判待 2h 门/full-quality |
| P5 证据套件 | full-quality / 2h 稳定门 / open-loop 双曲线：见 §6（数据槽） |
| SLO | 维持 SLO_UNDECIDED；本报告附完整吞吐-延迟曲线（§6.3） |

## §1 P1 因果裁决（0.28 认证栈）

### 1.1 容量预检（P1.0）
- bf16 @220K TP2 auto 池：**456,621 tokens = 2.03× 上下文**（容量可行；此前的 OOM 估算过于保守）
- kvarn 冻结预算 4.82GB：679,724 tokens = 3.02×
- fp8：boot 双尝试（默认/强制 FLASH_ATTN）均死于 flashinfer 0.6.16.post3 自带 CCCL 头与 cu13 nvcc 不兼容（`cuda_toolkit.h:41`）→ UNSUPPORTED（环境限制，证据 log-p1cap-fp8-B02 / -fp8fa-B04）

### 1.2 2×2 因果屏蔽（P1.1，Screen）
| 臂 | 配置 | 结果 |
|---|---|---|
| A | kvarn + target-only | **2/5**（TTFT 93.2s） |
| B | kvarn + DFlash2 k=7 | **2/5**（96.6s）——Phase 00 负结果复现 |
| C | bf16 + target-only | **2/5**（91.8s）——**输出与 A 逐字节相同**（`941235,900875`） |
| D | bf16 + DFlash2 | **2/5**（104.0s） |

判定表命中 **NOT_ATTRIBUTABLE_TO_KVARN**。单变量纪律：四臂同 overlay/PYTHONPATH/env/cache 规则，仅 kv dtype（+derived kv-mem=auto）与 spec 开关。

### 1.3 判别探针（转"查 fixture/model/runtime"分支）
- seed99（dig028 历史码集）@220K：bf16 **5/5**、kvarn **5/5**
- seed2 @220K：**5/5**
- **seed1 @128K：2/5**——失败与长度无关
→ **seed1/seed3 码集本身不可召回（夹具内容问题）**；DECISIONS #6 勘误成立。

### 1.4 P1.2 矩阵（Qualify：3 真 boot × 3 seed + seed99 + TTFT 3×3）
- kvarn/bf16 两臂 9/9 格完全确定（S1/S3=2/5、S2=5/5，跨 boot 零漂移）——Phase 00 跨 boot 债清偿
- seed99 参考码集 6/6 boot 全 5/5
- TTFT：kvarn 中位 **96.645s**（boot 漂移 0.07%）/ bf16 **104.219s**（0.03%）→ bf16 容量换精度价格 = **+7.8%**（注册为 0.29 Gate A-X same-KV reference）

## §2 Layer A（0.29 target-only 资格）

| 形制 | 0.28 参照 | 0.29 Layer A | Δ |
|---|---|---|---|
| TP1 D565 F512（Qualify 3-boot 中位） | 57.838（漂移 0.016%） | 57.863（0.010%） | **+0.043%** |
| TP1 P4K NS 中位 | 57.197 | 57.204 | +0.012% |
| TP2 D565 F512（资格臂） | 84.946 | 84.968 | +0.026% |
| verbatim | 100/100 ×3 | 100/100 ×3 | 全同 |

- **MRV2 实证**：`gpu_worker.py:429 "Using V2 Model Runner"`（TP1+TP2）；0.29 措辞勘误（非 "mrv2" 字面）
- 内核路径对齐：GDN 融合核→Triton fallback 双版本同因同路径（f16 conv cache 触发，无混淆）
- unit-a（embed-quant）移植验证：0.29 qwen3_5.py:245 原生缺失→2 行补丁落位，import+boot 实证

## §3 Layer B（0.29 + DFlash2 recal k=7）

| 项 | 0.28 spec | 0.29 spec |
|---|---|---|
| D565 F512（Qualify 3-boot 中位） | 145.008 | **145.012（+0.003%）** |
| spec 加速 vs target-only | 2.506× | 2.524× |
| ccdet 无损探针 | `0bd1ecd6…`（8/8 boot） | `0bd1ecd6…` |
| 接受率（per-draft-token / k=7） | 2.3176（33.11%） | 2.3402（33.43%，+0.33pp） |

- **四通路（0.28/0.29 × target-only/spec）探针输出同 hash** = 跨版本逐位无损；与 Phase 00 D1 确定性 hash 一致
- **unit-c 裁决**：0.29 首次 spec boot 死于 flashinfer 0.6.18 topk JIT（同 CCCL 根因）→ VERIFY 升级 REQUIRED，env 开关补丁已移植（`VLLM_DFLASH2_TORCH_TOPK=1`）
- graph-replay 证据：`--cudagraph-metrics` 不产 Prometheus 名（宽采样空）→ profiler 路径补证（§6.4）

## §4 Layer X / Layer C

### 4.1 Layer X bridge（0.29 长上下文资格，bf16 native）
- 臂：0.29 + patch(a,b,c) + bf16 + spec + 220K 生产形制
- 容量 1.42×（319K tokens）；MRV2 ✅
- needle（修正协议）：seed99 **5/5**、seed2 **5/5**、seed1 对照 **2/5**（与 0.28 逐态等价）
- TTFT 中位 **104.125s** vs same-KV 参照 104.219s = **−0.09%**（门 ≤+5%）

### 4.2 Layer C KVarN port（止损）
- 移植面：6 新文件（5157 行）+ 11/13 hook 干净 + 2 文件手工适配；6/6 导入零错；**KVARN backend 激活并可 boot**
- 4 次尝试（全留证）：#1 flush 形状崩（4D 池）→ #2 reshape 写入=确定性损坏 → #3 入口归一化=图捕获 OOM（池带页填充非连续，reshape 整池拷贝）→ #4 permute 嵌套=与 #2 逐字节同损坏
- 诊断：0.28 内核按 flat-tile+stride(0)/stride(1) 寻址；0.29 V2 分配器出**带页填充 4D**——正解需重写内核寻址（侵入 core 红线）
- 裁决：0.29 长上下文 = Layer X 承接；0.28+kvarn 保留生产认证；KVarN-on-0.29 入 Phase 03 Debt

## §5 补丁与环境台账

| 单元 | 内容 | 0.29 状态 |
|---|---|---|
| a | embed-quant 检查点加载（qwen3_5 ×2） | 移植 ✅（Layer A 实证） |
| b | dflash packed-quant KV-row dequant + dflash2 compile 修复 | 移植 ✅（Layer B 实证） |
| c | VLLM_DFLASH2_TORCH_TOPK 强制 torch.topk | 移植 ✅（Layer B 实证必移） |
| d | kvarn 内核/backend/hooks | 移植但 INERT（Layer C 止损；仅 kvarn_* dtype 激活） |
| e | VLLM_V2_CUDAGRAPH_MEM_MIB 显式预留 | 移植 ✅（model_runner 手工 hunk） |

- CLI 差异：`--kv-cache-memory` → `--kv-cache-memory-bytes`（per-GPU；not-None 忽略 gpu_mem_util）；help 改 ConfigGroup 制
- bfloat16/fp8 族两版本均显式可选；turboquant_* 上游近亲在（Layer C 参照系）
- 0.29 env 校验告警 `Unknown vLLM environment variable`（VLLM_DFLASH2_TORCH_TOPK 等 ported 变量）——警告级，功能正常

## §6 P5 证据套件（数据槽）

### 6.1 full-quality（rulers，0.29 候选 vs 0.28 同形制参照；同一 harness/同 server 形制 spec-32K-MS4）

| 轴 | 0.28 | 0.29（run1 / run2 复跑） | 判定 |
|---|---|---|---|
| HumanEval-164 pass@1 | **97（59.1%）** | 89（54.3%）/ **97（59.1%）** | 无回退——boot 间方差 ±4.9pp 主导首差（temp-0 下 batch 次序数值翻转边缘题）；复跑与 0.28 全同 |
| GSM8K-100 | 24% | 20% / 24% | 同上（±4pp 版本内摆动） |
| IFEval-50 | 26% | 36% / 38% | 0.29 名义更好（n=50 不显著） |
| XFC-200 | 75% | 75% | 全同 |
| BFCL-2000 | 0.0 | 0.0 | 轴不可用：两版本 server 均未开 tool-call 旗标（baseline-3.0 同为 0.0，形态先例）——列 Debt（tool-call 形态门） |
| longgen | — | 4333 chars、accept_rate 累计 0.4642 | 记录 |

- 环境注记：humaneval/gsm8k 首跑因 vllm29-env 缺 pandas/pyarrow 失败，已补装（env 变更入台账）
- **Gate-A 质量判定：PASS**（核心代码轴无显著回退；XFC 全同；IFEval 改善；BFCL 双版本同形态不可用）
- 与 llama.cpp 全精度基线（HE 84.8%）不可直接比——量化+形态差异，非本门对象

### 6.4 graph-replay 证据（profiler 路径）

**定档 EVIDENCE_PARTIAL**：
- Capture 实证：`Capturing CUDA graphs (PIECEWISE): 4/4` + `(FULL): 1/1` + **`Capturing dflash2 CUDA graphs (FULL): 1/1`**（speculator 专属图）
- 运行实证：spec-decode 计数器逐请求递增（drafts 482-488/臂、accepted 对应）→ speculator 每 decode 步执行
- 性能签名：145 tok/s（k=7 spec 速率仅 graph replay 路径可达）
- 缺口：逐 dispatch 计量——`--cudagraph-metrics` 无 Prometheus 出口（宽采样空×2），torch profiler 活动窗在 boot 期耗尽（优雅停机亦不 flush）→ 上游计量化列 Phase 03 Debt
- Gate 处置：不宣称 0.95 ratio 达标（NOT_DETERMINED），以 capture+计数器+签名三重间接证据放行至 Phase 02，Debt 清偿后补正式判定

### 6.2 2h 稳定门（混合流量 + canary）
<!-- STABILITY_TABLE -->

### 6.3 吞吐-延迟双曲线

**P220K（A-X profile，容量退化版）**：bf16@220K KV=319K tokens → **并发上限=1**，closed C2/C4/C8 物理不可行。
- C1 服务率 **0.00722 rps**（~138s/请求 = TTFT 104s + 128 tok 解码）
- 110% 过载点：arrival 0.0079 / achieved **0.0067 rps**（容量钳制）、TTFT P50 **278.8s**（排队膨胀 2.7×）、0 失败、completed 6<20 → P99=INSUFFICIENT_SAMPLES（冻结规则）
- 偏差记录：25–90% 子饱和点在容量-1 系统上与 C1 基线无信息差，未跑（容量裁定）
- SLO 含义：220K 档为"单飞行深度"服务形态，准入控制必须限制在途 1

**D565（S-profile）**：<!-- D565_CURVES -->


## §7 放行判定

<!-- FINAL_VERDICT：Gate A-S / A-X / Overall；Phase 02 建议 -->

## §8 勘误与流程事故

1. p1_causal stage2 dtype 映射 bug（臂标签误传 serve 参数）——修复后重跑
2. p2_layer_a `--runs` 单串传参 bug + makedirs 缺失——修复；0.28 参照臂残留 server 按登记 PGID 清场
3. verbatim 校验器**代码围栏剥离缺陷**（模型自发 ``` 围栏致整体移位误判 0/100）——修复+自检复过；首个真模型正向通路发现
4. p1_matrix evaluate() hits 字符串类型 bug——修复；数据无损
5. setsid 立即返回导致的 boot-exit 误读 + 稳定门等待循环漏 sleep——命令拼装勘误
6. Layer C a3 boot OOM ×2：TP2 换代间隙显存未泄净假说被干净 GPU 复现推翻——真因为 reshape 整池拷贝（止损证据链一部分）
7. **脱敏**：staging TP2 server-log-tail 含 `mq_connect_ip=本机内网IP`（2 文件）已按规则表替换；P6 归档批处理须规则化执行
8. 归档批处理首版对 needle/verbatim 目录误走全 schema（SCHEMA_FAIL 70 目录）——按 Phase 00 NDL 最小 manifest 先例救援归位

## §9 Phase 03 Verification Debt

1. KVarN-on-0.29：需上游布局契约对齐或内核寻址重写（Layer C 止损报告全留证）
2. FP8-KV（calibrated scale）资格：0.28 不可运行（CCCL）；0.29 未测（bf16 已可容 220K，优先级降）
3. KV 三路选型 Gate C（Native/FP8-calibrated/KVarN 分档：短上下文/日常长/极限）——P1 已供召回等价 + TTFT 价格 + 容量三组关键输入
4. graph-replay 计量上游化（`--cudagraph-metrics` 无 Prometheus 出口的缺口）
5. 2h 门 A-X 版（220K 混合流量）与 P220K open-loop 曲线（本轮若未完成）

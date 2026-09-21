# Phase 02 报告 — TP2 主基线深挖 → L2/X2 Profile + Gate B（nextgen-20260917）

- 计划：v1.2（机器契约修正版，8 项修正）；harness 权威指针 = `80e7d15` / runner safety `899eb5a`
- 环境：runtime029_phase02_baseline（终态快照 post-patch tree `4632d624…`/2537 文件，integrity CLEAN）；全 GPU 工作在 GPU3+4（TP2）与 GPU2（TP1 对照）；GPU0/1 与 :8000 零触碰
- Gate 定义：repro/gates-phase02.yaml（sha `a9477029…`，P0A 看结果前冻结）；两类 Gate = scalar_optimization（≥3% sign-aware）+ policy_envelope（预冻结约束）；schema 1.2（screen_decision / evidence_quality / observation_class）
- 主链实际执行：P0A 冻结 → P0B 拓扑 → B0 三形制 → TP1CTL → batch1（scalar）→ dynk → batch2（policy）→ P3-Qualify → P32K 方差/认证 → Gate B → P4-SLO + ceiling

## §0 结论速览

| 项 | 结果 |
|---|---|
| **Gate B Overall** | **PASS**（B-L2 PASS ∧ B-X2 PASS）——TP2 适合成为交互/长上下文主基线 |
| B-L2（P32K 形制） | PASS：ttft_p50(C1) **−18.2%** ✓ + goodput(C2) **+596%** ✓（TP1 P32K-C2 预填充串行塌缩 14.3 vs TP2 99.6 tok/s）；tpot(C1) −7% 如实记录（TP1 保单流 decode 优势）；ttft_p95(C1) −24.2% 反向大改善 |
| B-X2（128K/220K） | PASS：seed99 5/5 全档；220K TTFT 103.95s（−0.17% vs 104.125 门）；容量边际 1.42×/1.78×；表述=designated X2 domain |
| **composite_L2** | **= B0 配方**（0.29+W4A16+DFlash2 k7+TP2+draftTP1+32K+bf16+NBT2048+MS4）——全部 scalar 胜者被认证回退，forward-addition 集合清空 |
| **composite_X2** | = B0 配方 + **q4 在途护栏**（唯一 envelope 胜者；x220 在途=1 已证 −0.17%） |
| 9 向 Screen 终判 | IN：NBT3072→**认证回退**、DTP2→**认证回退**、K5→pos1 地板回退；UNSUPPORTED：match-unit；OUT：其余全部；envelope：q4 IN、x220 PASS、MS8 C8 吞吐档 envelope 点 |
| dynamic-k | k8 **CLOSED**（CG capture 8 < verify 9）；k6 OUT（全轴被支配）；k7 在位维持；**P32K spec-off 双优**（TONLY decode +21-30%、暖 TTFT +33% vs 全 spec 臂）→ Phase 03 正式 A/B |
| P32K 认证 | NBT3072 @P32K **−3.29% 认证回退**（Screen +17.2% 信号证伪=慢态分母伪影）；B0R 3-boot spread 0.14% |
| 平台冷启动惩罚 | **新平台现象**：idle 后首 boot −18%（57.5 vs 69.9 tok/s）；back-to-back spread 0.14% → 认证协议修正（WARMUP 弃置） |
| SLO | **UNDECIDED 解除**：L2（D565+P32K）+ X2（P128K）全档双曲线（closed C1-C8 + open 5 点 arrival 列），全点 0 503（**Erratum EP03-A2**，见 §11：曲线≠SLO Authority，正式状态仍 SLO_UNDECIDED） |
| ceiling 晋级链 | P245K seed99 **5/5 PASS**（TTFT 128.5s）→ **P262K seed99 5/5 PASS（TTFT 133.7s）= 模型绝对上限 262,144 工作**；两档 CEILING_OBSERVATION |
| TP1-C4 补测 | PENDING（GPU2 全程被外部任务占用）——B-L2 aggregate 他轴唯一未闭合项 |

## §1 P0A 冻结 + P0B 拓扑 + B0 基线（4d4e7ac…）

**P0A**（无 GPU）：runtime029_phase02_baseline 终态快照；schema 1.2 additive；gates-phase02.yaml 全数值化；能力探针（bss V2/MRv2 配置级可行、dynamic-k 对 dflash **源码级不支持**、admission 双旗标、retention/match-unit 实名、AR 三态、CG FULL 枚举）；runner 三件套 p02_common/p02_screen/p02_evaluate（`_total` 精确名纪律+自测；sign-aware 冒烟复算 Layer A +0.04% 一致）。

**P0B**：busbw 双测 14.34/14.37 GB/s@256MB（|Δ|=0.21%）——同对重复即对照；对照对 2+X 未获得（GPU2 被 bakeoff 占用窗口），按 gates 默认 **维持 3+4**（topo 全 PXB/NUMA0 等价注记）。期间外部容器族（rpg-bakeoff-*）梯度进驻 GPU2-7，本战役零触碰、等待+灵活对（用户拍板 3+4 > 2+5 > 2+6 > 2+7）。

**B0 三形制**：
- B0-L32 Qualify 3-boot：D565-F512-C1 agg 中位 164.63 / decode 177.4（spread 1.40%）；C4-NS 201.71（spread 3.20% 旗标）；P4K cold/warm 114.89/115.28
- B0-X128：C1 真并发 TTFT 50.6/106.3s、C2 max_running=2；容量 374,381 KV tok
- B0-X220：needle 三态冷 TTFT 实证 104.18/104.25/104.30（vs Layer X 104.125 = +0.1%）
- needle 三态签名精确复现 Phase 01（seed1=2/5 逐位同款、seed99 全 5/5、seed2@220K 5/5）；**新数据点 seed2@128K=2/5**（码集×长度非正交，X128 阳性对照以 seed99 为准）

**TP1CTL**（B-L2 分母）：D565-F512-C1 decode 144.9（vs Layer B 145.012 −0.08% 交叉验证过）；P32K C1 TPOT/decode 61.9 tok/s、冷 TTFT ~12.7s、暖 0.39s；C2 冷 goodput 0.061 rps（预填充串行，TTFT p50 15s）。勘误三条固化：VLLM_DFLASH2_TORCH_TOPK=1 入配方、L32→36864、空-成功陷阱 evidence-guard。

## §2 9 向分类型 Screen 终判（batch1 + batch2，六态归档见 §8）

| 向 | 类 | screen_decision | 终态（认证后） | 证据 |
|---|---|---|---|---|
| a. draft TP 2 | scalar | IN | **OUT**（认证回退 C1 **−4.39%**，Screen +3.7-4.1% 反转） | P02-SCREEN/batch1 + P03-QUALIFY |
| b. NBT 阶梯 | scalar | NBT3072 IN；1024/4096 OUT | NBT3072 @P32K **−3.29% 认证回退→OUT**；@P4K **+10.7% 认证维持**（短提示轴独立候选，Phase 03） | 同上 + certify |
| c. CUDA Graph | scalar | FULL8/FULL16 OUT | OUT（FULL 反慢 C1 −3.5%、cap16 C8 −7.7%；auto/cap8 在位即优） | batch1 |
| d. all-reduce 三态 | scalar | ARFI/ARNOCA OUT | OUT（最佳态 +1.4~2.5% < 3% 噪声线，正向趋势留档） | batch1 |
| e. bss | scalar | OUT（能力反转） | boot 级 **SUPPORTED 实证**（MRv2+spec+bss 共存，推翻源码 V1 预期）但 C2 −6.2% → OUT | batch1 |
| f. max_num_seqs 三角 | policy | MS1/MS2 OUT；MS8 OUT_for_L2 | MS4 在位维持；MS8-C8 419-438 tok/s 吞吐档 envelope 点留 Phase 04 | batch1 |
| g. admission | policy | **q4 IN**；q8/q32 OUT（惰性） | **composite_X2 唯一护栏**：零排队、503 单调可重试、过载 p95 双钳（p4k 1.85 vs 6.52 / p32k 19.7 vs 24.0）；**x220 在途=1 PASS**（TTFT −0.17%、preempt/oom/err 全 0、verbatim 100/100） | batch2 part2 |
| h. prefix retention | policy | OUT | 显式值 warm 大退步（0=+560%/1024=+85%）；churn 存活 6.2× 观察 → Phase 03 稳态 A/B | batch2 part1 |
| i. prefix match unit | policy | **UNSUPPORTED** | 一切显式值触发 SW 管理器块对齐强制（告警 forensics：显式传旗标即警，省略干净）；四臂零行为差——0.29 旗标面对混合架构无效，留档 capabilities | batch2 part1 |
| +dynamic k | scalar | k8 CLOSED / k6 OUT / k5 IN_conditional | K5 pos1 地板 3-boot 复现 +12.7pp > 8pp → **回退 K7**（规则张力如实记录：pos1 高=总接受率高的机制本身） | P02-SCREEN/p2-dynk |

## §3 dynamic-k + 投机结构（P2）

- k8 **CLOSED**：capture sizes [1,2,4,8] < verify batch 9 → 逐步 graph miss（ms/step 55.1 vs 18.6、decode −65%）；位置 8 接受非零但双条件不同时满足
- k5 条件入 Qualify 后回退；k7 在位维持。接受率地板全过（K5 0.446/0.383）
- **TONLY 结构性发现**：D565 spec 净赢 2.13×（TP2 价值由投机驱动；TP2-TONLY 85.1 < TP1-spec 144.9）；**P32K 全 spec 臂 decode 输 TONLY 21-30%、暖 TTFT 输 33%**（draft 32K prefill 罚 + verify 47.8ms/step vs 12.75ms/tok）——L2 主曲线的结构性 caveat，Phase 03 spec-off 正式 A/B 建议
- 投机净收益台账：k+1 ≈ −8,700 KV tok；spec 全栈 ≈6.4 GiB/GPU；接受计数器自洽 sum(pos)==accepted、emitted/client 0.97-0.99；分桶 PARTIAL（聚合计数器无逐请求差分）

## §4 P32K 双峰 → 平台冷启动惩罚 → 认证协议修正（方法论资产）

- 现象：boot 级确定性双峰（58.1 vs 67.6，16%），boot 内 ±0.1%；编译态/容量/臂配置均不映射
- 8-boot 方差表征：**唯一慢 boot = 10h idle 后首个 boot**（57.5 vs 69.9，−17.8%）；随后 7 个 back-to-back boot spread **0.14%**；D565 同向 +5.3% → 平台级冷启动惩罚
- **认证协议修正**（三要素升级）：cache 钉死 + 暖机 + **idle 后首 boot 弃置（WARMUP）**、back-to-back 入证
- 历史跨窗单 boot 数字一律补 ±18% 平台态 caveat；**Screen→Qualify 反转 ×2**（NBT3072-P32K +17.2%→−3.29%、DTP2 C1 +3.7%→−4.39%）制度化：单 boot Screen 信号 <2× 门槛一律 provisional
- 生产含义：长上下文冷启动慢态 ~18% → Phase 08 热机手册素材

## §5 双 lineage forward-combine 终态

- **composite_L2 = B0 配方**：DTP2 认证回退 / K5 pos1 地板 / NBT3072 P32K 认证回退 → 集合清空（每步"胜者"均死于认证形制，反向验证了 3% 线+多 boot 门槛的必要性）
- **composite_X2 = B0 + q4 在途护栏**（非 perf 变更）；portable 集合空（NBT3072@X128 recheck 因主轴已 OUT 未跑）
- 交互台账：无叠加交互可记（无组合臂存活至叠加步）

## §6 Gate B 判定（raw/staging/P03-QUALIFY/gate-b-verdict.json）

分母形制：TP2=composite_L2=B0（3-boot 认证 spread 0.14%）；TP1=TP1CTL 同栈 3-boot；状态配对=慢态窗互比（TP1CTL/PAIR34/GATEB-G2）+ 快态全方向更优验证。

- **B-L2 PASS**：主轴 ttft_p50(C1-P32K) −18.2% ✓、goodput(C2-P32K) +596.3% ✓（TP1 预填充串行塌缩 vs TP2 交织）；other_key ttft_p95 −24.2% ✓；tpot(C1) TP1 保留 −7.0%（如实记录，与"聚合吞吐 TP1 对照保留"口径一致）；TP1-C4 aggregate 轴 PENDING（GPU2 外部占用）——pass_rule 不依赖该轴
- **B-X2 PASS**：needle seed99 128K/220K 全 5/5；TTFT 220K 103.95（−0.17% vs 门 104.125）；容量边际 X128 1.42× / X220 1.78×；C4/C8@128K CAPACITY_LIMIT 端点；表述=**designated X2 domain**（TP1 128K 对照未跑，不称 exclusive）
- **Overall PASS**；质量线：verbatim 多臂 100/100、needle 三态签名逐位复现

## §7 P4-SLO 双曲线 + ceiling 晋级链（raw/staging/P04-SLO/）

**SLO_UNDECIDED 解除**（全档双曲线 + arrival 列 + CAPACITY_LIMIT 端点）——*Erratum EP03-A2（2026-09-21 追加，见 §11）：本节完成的是 SLO 定标曲线义务，"解除"措辞由勘误修正，正式 SLO 状态仍为 SLO_UNDECIDED*：

| 形制 | closed | open（0.25-1.1× Poisson） | 备注 |
|---|---|---|---|
| L2-D565（MS4） | C1-C8 TPOT 0.0182→0.0552s | p95 0.28-1.57s，0 503 | sat_est 0.41 rps；p95 非单调=Screen 级小样本 |
| L2-P32K（MS4） | C1-C8 TPOT 0.048→0.3195s | p95 10.2-34.5s，0 503 | sat_est 0.0505 rps |
| X2-P128K（MS2） | C1 TTFT 53.3s/TPOT 0.138 | p95 132-310s，0 503 | C4 工作点 526K > 374K KV → **CAPACITY_LIMIT**（C4/C8 实测排队补充数据留档） |

**ceiling 晋级链**（seed99，MS1 在途=1 生产形态）：P245K **5/5 PASS**（TTFT 128.5s，KV 394,941，驻留 1.57×）→ **P262K 5/5 PASS（TTFT 133.7s）**——prompt 靶 261,888 + 模板 + 64 输出 = 262,095 ≤ **262,144 = max_position_embeddings 模型硬上限**。两档 **CEILING_OBSERVATION**（正式 3-boot×3-seed 认证归 Phase 03）。262K 参数化取证：len 268288 > 模型上限被 ModelConfig 拒绝 → 靶 262000 fixture 装配实测 262,153（超靶 +153）+64 → HTTP 400 → 终靶 261,888 离线 tokenizer 预验证后一次通过。

## §8 六态归档总表（schema 1.2）

| 方向/实验 | 实验六态 | screen_decision | candidate_decision | evidence_quality |
|---|---|---|---|---|
| runtime freeze / B0×3 / TP1CTL / GATEB / CERT / SLO / ceiling | VALID_PASS | — | PASS（各自 Gate/Profile） | COMPLETE |
| k8 能力复核 | VALID_PASS | CLOSED | REJECTED（k8 关闭） | COMPLETE |
| NBT3072 P32K | VALID_PASS | IN→falsified | REJECTED（−3.29% 认证） | COMPLETE |
| NBT3072 P4K | VALID_PASS | IN | DEFERRED_TO_PHASE03（短提示候选 +10.7%） | COMPLETE |
| DTP2 | VALID_PASS | IN→falsified | REJECTED | COMPLETE |
| K5 | VALID_PASS | IN_conditional | REJECTED（pos1 地板）/K7 回退 | COMPLETE |
| k6/CG/AR/MS/retention/bss | VALID_PASS | OUT | REJECTED | COMPLETE |
| admission q4 / x220 | VALID_PASS | **IN** | PASS（envelope） | COMPLETE |
| match-unit | VALID_PASS | **UNSUPPORTED** | —（旗标面无效留档） | COMPLETE |
| graph-replay 计量 | VALID_PASS | — | — | **PARTIAL**（上游无逐 dispatch 计量） |
| 接受率分桶 | VALID_PASS | — | — | **PARTIAL**（聚合计数器无逐请求差分） |
| TP1-C4 aggregate | NOT_RUN | — | PENDING_SUPPLEMENT | MEASUREMENT_NOT_AVAILABLE（GPU2 外占） |

## §9 Phase 03 Debt（移交清单）

1. **TP1-C4 补测**（B-L2 aggregate 他轴闭合；GPU2 释放即补，修正协议形制）
2. **P32K spec-off 正式 A/B**（TONLY 双优 21-30%/33%——L2 主曲线最大潜在再赢面）
3. NBT3072 短提示轴独立候选（P4K +10.7% 认证；X128 recheck 未跑）
4. ceiling 245K/262K 正式认证（3-boot×3-seed）+ 238K+ 全档
5. K5 pos1 地板规则张力复议（规则本意 vs 机制现实）
6. retention churn 稳态画像 A/B（6.2× 存活观察）
7. graph-replay 逐 dispatch 计量、drafter/verify 分解、接受率逐请求分桶（上游能力缺口）
8. MS8-C8 吞吐档 envelope 点（Phase 04 拓扑赛复访）
9. 平台冷启动热机手册（Phase 08，−18% 慢态）
10. seed2@128K=2/5 码集×长度非正交——needle 协议 seed 矩阵扩展
11. X2 P128K C2 第二请求 TTFT 翻倍形态（若生产需 C2 档需调 MS/NBT 重测）

## §10 收口

- 生产切换不自动发生（铁律 9）：本相位结论=候选 profile，Phase 08 窗口拍板
- 0.28+kvarn 认证继续保留；0.29 生产配方冻结件 `repo/eval/vllm/cuda13/usable-concurrency-20260916/` 不变
- 证据全集：raw/staging/{P02-SCREEN,P03-QUALIFY,P04-SLO,SCEIL*,V29-T2-*,V29-T1-*}；repro 链 tools/{p02_*,p1_batch2_*,p3_*,p4_*,boot029_nextgen}.py|sh（断点续跑形制）

## §11 勘误（Phase 03 P0A 正式追加，2026-09-21——只追加不改写上文原文）

**EP03-A2（SLO 状态措辞）**：Phase 02 完成的是 SLO 定标所需 throughput-latency curves（closed C1-C8 + open 5 点）；**未形成生产 SLO Authority**（无预冻结的正式生产 TTFT/TPOT/P95 goodput 数值判定门）。正式 SLO 状态仍为 **SLO_UNDECIDED**（MANIFEST `slo_status` 为单一 Authority，保持 SLO_UNDECIDED 不变）。§0 与 §7 的"解除"措辞以本勘误为准。

**EP03-A1（runtime freeze 空 lock 取证缺陷）**：`repro/env029/freeze-phase02-baseline.txt` 在 Phase 02 冻结时实际为 0 字节（sha256=`e3b0c442…`=空文件哈希）。根因：`p0a_runtime_freeze.py` 用 `python -m pip freeze --all` 做包清单，而 uv venv `/data/tools/vllm29-env` 无 pip（`ModuleNotFoundError: No module named pip`）→ rc≠0、stdout 空；旧工具不查 returncode 即写空文件并继续（fail-open）。Phase 03 P0A.1 已按双路契约修复（`uv pip freeze --python` 主 + `importlib.metadata` 交叉，PEP 503 规范化 name→version 比对，rc/空输出/包数下限/关键包漂移全 FATAL，temp→校验→atomic rename）。重审计结论：**EVIDENCE_REPAIR 非 ENV_DRIFT**——vllm tree sha `4632d624…`（2537 文件）、patch-unit 18 件 SHA、台账 sha_after、symbol provenance、关键包版本（vllm 0.29.0/torch 2.13.0/transformers 5.17.0/flashinfer-python 0.6.18/triton 3.7.1/pandas 3.0.6/pyarrow 25.0.1）与 Phase 02 认证基线**零漂移**；freeze 文件重写为 199 包双路一致清单（sha256=`d6ee86e9…`）。证据：`repro/env029/runtime029-phase03-inheritance.json` + `inventory-importlib-phase03.json`。

# Phase 04 报告 — 权重量化与分层混合 → Q-Profile Pareto + Gate D（nextgen-20260917）

- 计划：v1.0 执行合同（用户 2026-09-22 十三节批准）；harness 权威指针 `80e7d15` / runner safety `899eb5a` 继承
- 环境：runtime029 只读继承（P0A 完成门全过，commit `f79a102`）；KV 全程冻结 NATIVE_BF16；GPU 全程 GPU3+4（GPU2 外占 TP1-C4 机会式未触发）；GPU0/1 与 :8000 零触碰
- Gate 定义：repro/gates-phase04.yaml（sha `51e32497…`，看结果前冻结）；schema 1.4（quant_provenance 11 字段 + weight_profile）
- 构建环境：fp8c-build 容器（Docker python:3.12-slim + uv venv；llmcompressor 0.12.1a/compressed-tensors 0.18.0/torch 2.13.0+cu13；gcc 补装）

## §0 结论速览

| 项 | 结果 |
|---|---|
| **Gate D** | **3 Q-Profile 定案**：QP-INTERACT(Q0→S1/L2) ∧ QP-LONGCTX(Q1M→X2) ∧ QP-BATCH(Q4C→高并发路由)；hard eligibility Q0/Q1M/Q4C 全过 |
| **W8A16** | **REJECTED_FOR_QUALITY**（needle s2 配对退化 1 次 0/5 全灭 + IFEval −4.7pp）——"质量准上界"预设被实证推翻；被 Q4C 支配双重出局 |
| **Q4C（W8A8-FP8 dynamic）** | 质量全轴持平或微升（HE +2.4/GSM +3.3/IFEval +1.3/XFC +1.5，needle 零退化）+ p4kC4 **+26%** + J/tok 2.188 最优；128K=CAPACITY_LIMIT（实测 max_model_len 118784） |
| **Q1M（敏感度分层）** | GSM holdout **+6.7pp**（三 boot 全高）+ 128K decode **+37%** + p32kC1=Q0 无损；HE −3.2pp 在 Q0 自身 8.9pp 噪声带内 |
| 敏感度图 | 304 模块；mlp.gate/up=W4 敏感主力（60%+ 误差贡献）；g64 恢复直接兑现 GSM 轴 |
| kernel 实证 | 全候选 MarlinLinearKernel WNA16 路径；FP8 权重 GEMM ≠ FP8-KV 的 flashinfer JIT 墙 |
| Phase 05 冻结件 | repro/quant-phase04/phase05-handoff.json（三 Profile artifact+SHA+精度图+路由边界） |

## §1 P0A 契约冻结

- **reconciliation**：三方 HEAD=0d3a978 一致、树净；STATUS Next Task 漂移修正（Phase 03 残留→Phase 04 链）
- **freeze 工具修复**：无（Phase 03 已修复，本相位零漂移）
- **Q0 forensic**：21 文件 SHA、module dtype map（W4g128 主体+lm_head INT8 就地+embed INT8 就地+ignore 207=vision 110/GDN in_proj 96/lm_head 1）、quant_*.py 历史链 SHA、recipe 缺失如实记录（AutoRound 原始 recipe 不在盘——TRAIN-NOTES 文字记录在案，不补造）
- **teacher 血缘 VERIFIED_LINEAGE**（三重证据）：merge_meta（merged_from=checkpoint-4840, base=Qwen3.8-27B-BF16）+ tokenizer 三件 SHA 全等/config 非量化字段全等 + **权重级 spot 抽查**（compressed_tensors PackedQuantizationCompressor.decompress vs teacher bf16：cosine 0.994-0.995/rel 10-11%，attn/GDN/MLP 三模块族=W4g128 签名一致，float64 分块点积）
- **能力探针**（源码级）：W8A8-FP8 SM89 合格（min_capability=89）；W4A8-FP8=90 hopper only **架构性排除**；NVFP4/MXFP4=75/80 软件路径 emulation；llmcompressor config_groups 分层支持；W8A16 oneshot 可行
- **三分数据**：quant_calibration_sensitivity_dev（复用 phase03 corpus 64 样本）/screen_quality_dev（needle s99@32K/128K + verbatim + HE[0:40]+GSM8K[0:80]）/final_quality_holdout（sealed：needle s2/s5 多档 + HE[40:]+GSM8K[80:320]+IFEval[0:150]+XFC 全量）+ checker PASS
- **工具自测全过**：ph4_energy_report（合成 1050J 精确）/ph4_sensitivity_collector（闭式 MSE/cos 精确=rel 0.0000 + dry-run 16/48 分列）/ph4_tooljson_micro（判据器正反例）
- **Debt 9 项 disposition** 落 gates（TP1-C4=OPPORTUNISTIC 未触发/FPX-KV=DEFERRED_CONDITIONAL/隔离=DO_NOW_CLOSED/K5=CLOSED_AS_RULE_ADOPTED/churn+租户隔离=DEFERRED→Phase06/graph-replay=CONDITIONAL/MS8-C8=TRANSFERRED→Phase05/SLO238+=DEFERRED）

## §2 P0B 探针与构建

- **Q4-OFFICIAL 探针 ALIVE**（CROSS_BASE/PROBE_ONLY）：boot 成功 weights 15.29GiB/卡；**kernel 实选 MarlinLinearKernel for CompressedTensorsWNA16** + `+quant_fp8` 激活融合——FP8 权重 GEMM 与 FP8-KV 的 flashinfer JIT CCCL 墙无关（源码预判证实）；verbatim 100/100、micro 19/20（tj05 底座指令语义）
- **W8A16 构建（两轮废弃后落地）**：v1 废弃（GDN in_proj 被量化=污染准上界）；v2 废弃（**lm_head 绑定权重 packed 不可加载**——Q0 的 int8 头依赖 serving 树补丁基建，构建侧教训）；v3 终版 aggregate `ae72e630…`：int8 g128 sym、精度图=Linear W8/lm_head+embed+GDN in_proj/visual=bf16
- **Q4C 构建**（aggregate `f1787fa9…`）：compressed-tensors W8A8-FP8 dynamic（weights e4m3 channel sym + input per-token dynamic）
- **Q1M/Q2M 敏感度驱动构建**：Q1M=19×W8 首尾+60×W4g128+135×W4g64（aggregate `6fa23c76…`）；Q2M=192×W4g128+64×W8 attn+48×W4g64 gdn（aggregate `aafc4a3b…`）
- **五候选 boot smoke 全 ALIVE**（全 Marlin WNA16 路径、verbatim 100/100、micro 18-19/20 同款两项指令边缘 tj06/tj12）
- **NVFP4 = NOT_BUILT_EMULATION**（SM89 无 FP4 硬件+在盘无 checkpoint+研究档不投预算）
- **boot 能量分账**：官方 FP8 29.7kJ/W8 28.1kJ/Q4C 30.5kJ（450W cron 窗全记录）
- 构建事故与修复全留痕：scheme 五轮 API 形态发现（scheme→config_groups→processor→dataset 对象→max_memory）+ 容器 gcc 补装（GDN triton JIT）+ root 属主 chmod

## §3 P1 敏感度图

- **304 模块零跳过**（16 full-attn ×4 + 48 GDN out_proj + 64×3 MLP）；GDN in_proj 家族不在图内（bf16 政策模块，正确排除）
- **family 敏感度排名（int4_g128 hess 贡献）**：mlp.gate 486M > mlp.up 446M > attn.q 283M > mlp.down 136M > attn.o 44M ≫ attn.k/v/gdn.out_proj（<10M）
- **结构洞察**：MLP gate/up 是 W4 敏感主力（量化误差 60%+ 集中于此）；GDN out_proj 最钝；与 Q1/Q2 恢复设计直接挂钩
- 校准=quant_calib_sensitivity_dev 64 样本（teacher=merged-bf16 offload 双卡 20GiB+CPU）

## §4 P2 矩阵 Screen（六轴）

| 臂 | d565C1 | p4kC4agg | p32kC1 | 128kC1 | J/tok(p4kC4) | 128K 容量 |
|---|---|---|---|---|---|---|
| **Q0** | **182.6** | 161.9 | **69.9** | 18.5 | 2.268 | ✓ |
| W8 | 112.3 (−38%) | 175.0 (+8%) | 51.2 | — | 2.393 | ✗ 墙 |
| **Q4C** | 98.4 (−46%) | **203.6 (+26%)** | 47.8 | — | **2.188** | ✗ 墙 |
| **Q1M** | 114.4 (−37%) | 159.5 (−1.5%) | **69.9 (=Q0)** | **25.4 (+37%)** | 2.585 | ✓ |
| Q2M | 126.0 (−31%) | 166.1 (+2.6%) | 58.6 (−16%) | 26.6 (+44%) | 2.446 | ✓ |

- **容量墙双实证**：W8A16 131072 形式 boot OOM（载入 17.4GiB/卡）；Q4C `max_model_len 118784`（KV 4.52>4.15GiB）——VRAM 换精度的 Pareto 硬数据
- **勘误**：p128k=131072 装配溢出（+52 模板+64 输出>131072 全 400）→ 新 fixture p128kt=130900（离线验证 131041≤131072）；p128k 冻结不改历史
- Q0 d565=182.6 与 Phase 02 认证 182.4 交叉验证一致；Q0 p32kC1=69.9 与 P0B spec-on 认证 69.84 一致
- **shortlist**：Q0（交互/全档）+ Q1M（128K 长上下文）+ Q4C（C4 吞吐/能效）；W8 被支配留作质量参照；Q2M 角色同档出局（P32K 主轴 Q1M 无损胜出）
- 静态 OOD 全 CLEAN（4 artifact+Q0：零 NaN/Inf、零 scale 异常、dtype 结构与精度图一致）

## §5 P3 Qualify + holdout 首开（4 server × 3 boot 全 valid）

**Q0 噪声基线定标**（三 boot spread）：XFC 0.5pp / GSM-holdout 1.2pp / IFEval 6.0pp / **HE-holdout 8.9pp**（boot 生成抖动）——质量门退步判线 = max(2pp, Q0 spread)（gates epsilon"引用 harness 重复性"条款的实证落地）；needle s2@128K = Phase 02 已知闪烁签名 [5/5, 2/5, 5/5]，s5 稳定。

**holdout 中位（%）与 vs Q0**：

| 候选 | HE-h | GSM-h | IFEval | XFC | needle s2/s5 | 判定 |
|---|---|---|---|---|---|---|
| Q0 | 55.6 | 20.4 | 40.0 | 74.0 | 闪烁/全过 | 基线 |
| Q1M | 52.4 (−3.2, 噪声带内) | **27.1 (+6.7)** | 40.7 | 73.0 (−1.0) | 全 5/5/全 5/5 | **PASS** |
| Q4C | **58.1 (+2.4)** | 23.8 (+3.3) | 41.3 | **75.5 (+1.5)** | 全 5/5/全 5/5 | **PASS** |
| W8 | 56.5 | 23.8 | **35.3 (−4.7)** | 75.0 | **[5/5,0/5,0/5]**/全过 | **FAIL**（配对退化 1 次） |

- W8 的 s2 0/5 全灭形态（非 Q0 的 2/5 闪烁形态）+ IFEval −4.7pp = int8 g128 的真实质量警报
- micro 20 题安全门四候选全部 18/20 同款（tj06/tj12 同源血缘指令边缘——非结构破坏）

## §6 Gate D（raw/staging/PH4-P4/gate-d-verdict.json，机器判定）

- **hard eligibility**：Q0 ✓ / Q1M ✓ / Q4C ✓ / W8 ✗（needle s2 配对退化 1 次——Q0 同 boot 过而 W8 0/5 全灭；配对判读规则严格执行）
- **epsilon-Pareto 六轴**（吞吐/prefill 3%、能效 5%、质量 1pp 带、VRAM=容量墙硬差异）：Q4C 能效 2.188 vs Q0 2.268（−3.5% 在 5% 带内=等价）；Q1M p32k 0.1% 带内等价、128K +37% 出带真实优势
- **三 Q-Profile**（无综合总分、无 bit 排名）：
  - QP-INTERACT = Q0（S1/L2 底座）
  - QP-LONGCTX = Q1M（X2；GSM bonus + 128K +37%）
  - QP-BATCH = Q4C（高并发路由；容量域 ≤~118K）
- **排除**：W8（质量警报+被支配）/Q2M（角色同档出局）/Q3（架构排除）/Q5（emulation 不建）
- **路由边界**：短 prompt 交互→QP-INTERACT；≥32K 长上下文→QP-LONGCTX；C4+ 批处理→QP-BATCH

## §7 六态归档（schema 1.4）+ Debt

| 实验 | 六态 | weight_profile | candidate | evidence_quality |
|---|---|---|---|---|
| Q0 forensic/血缘 | VALID_PASS | Q0 | — | COMPLETE |
| Q4-OFFICIAL 探针 | VALID_PASS | — | PROBE_ONLY（cross-base） | COMPLETE |
| W8A16 构建+矩阵+qualify | VALID_PASS | W8A16 | **REJECTED_FOR_QUALITY** | COMPLETE |
| Q4C 构建+矩阵+qualify | VALID_PASS | Q4 | **PASS（QP-BATCH）** | COMPLETE |
| Q1M 构建+矩阵+qualify | VALID_PASS | Q1 | **PASS（QP-LONGCTX）** | COMPLETE |
| Q2M 构建+矩阵（screen 级） | VALID_PASS | Q2 | REJECTED（角色同档出局） | COMPLETE |
| Q3/W4A8-FP8 | UNSUPPORTED | Q3 | —（min_cap=90 架构） | COMPLETE |
| Q5/NVFP4-MXFP4 | NOT_RUN | Q5 | —（emulation 不建） | COMPLETE |
| TP1-C4 | NOT_RUN | — | OPPORTUNISTIC 未触发 | MEASUREMENT_NOT_AVAILABLE |
| 静态 OOD | VALID_PASS | 4 artifact+Q0 | —（全 CLEAN） | COMPLETE |

**Debt 移交**：TP1-C4（继续顺延）；FP8-KV 上游解锁（fp8c-build 容器保留——解锁后可与 QP-BATCH 叠加复评）；租户隔离/强驱逐 churn→Phase06；MS8-C8→Phase05；graph-replay=CONDITIONAL 未启用；BFCL 仍 MEASUREMENT_NOT_AVAILABLE（micro-suite 只作安全门）。

## §8 收口

- **Phase 05 冻结件**：repro/quant-phase04/phase05-handoff.json（三 Profile artifact+SHA+精度图+路由边界+KV=NATIVE_BF16+runtime 配方；仅凭仓库可答全部拓扑赛输入）
- 事故与修复全留痕：p128k 装配溢出（p128kt 勘误）、lm_head 绑定权重 packed 教训（v2 废弃）、llmcompresson 五轮 API 形态发现、容器 gcc/权限、argv 溢出改 shell 循环
- Q1M 敏感度驱动设计的方法论资产：layer-sensitivity.csv + ph4_design_mixed 提案器 + ph4_sensitivity_collector（闭式精确自测）——Phase 06+ 可复用
- fp8c-build 容器保留（QP-BATCH artifact 溯源 + FP8-KV 解锁链路依赖）
- 生产切换：铁律 9——本相位结论=候选 profile，Phase 08 窗口拍板

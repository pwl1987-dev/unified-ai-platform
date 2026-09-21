# Phase 03 报告 — KV Cache 对决 → 三档 Profile + Gate C（nextgen-20260917）

- 计划：v1.1 执行合同（用户 2026-09-21 批准：13 条执行前修正 + 5 条执行契约）；harness 权威指针 = `80e7d15` / runner safety `899eb5a` 继承
- 环境：runtime029 只读继承（P0A.1 fail-closed 重审计 **EVIDENCE_REPAIR**，repro/env029/runtime029-phase03-inheritance.json）；0.28 参考栈 = vllm28-env（只读）+ boot028 冻结配方；GPU 工作全在 GPU3+4；GPU2 全程被外部任务占用（TP1-C4 顺延）；GPU0/1 与 :8000 零触碰
- Gate 定义：repro/gates-phase03.yaml（sha `234253…`，P0A 看结果前冻结）；schema 1.3（kv_route/route_eligibility/capability_label/cross_runtime_reference/calibration_provenance）
- 勘误基线：Phase 02 报告 §11（EP03-A1 空 freeze 取证缺陷 / EP03-A2 SLO 措辞——**正式 SLO 状态仍 SLO_UNDECIDED**，MANIFEST 单一 Authority）

## §0 结论速览

| 项 | 结果 |
|---|---|
| **Gate C** | **三档全 PASS**：short PASS ∧ daily PASS ∧ extreme PASS——0.29 主栈 KV 选型 = **NATIVE_BF16**（FP8 两路 UNSUPPORTED 缺席由 NATIVE 承担，分档规则生效） |
| **FP8E4/FP8C** | **UNSUPPORTED**（三 boot 取证：flashinfer 0.6.18 fp8_e4m3 prefill 内核 JIT CCCL×cu13 nvcc 墙；TRITON_ATTN env 不改路径；与 0.28 栈同根因家族）——FP8C artifact 构建取消，链路就绪待上游（Phase 04+ 债） |
| **238K/245K** | **正式认证 PRODUCTION_SAFE**（3 boot × 3 seed 全 5/5；KV 余量 +65.4%/+61.0%；TTFT 116.3/121.3s ±0.2%） |
| **262K** | **HARD_CEILING_CAPABILITY_PASS**（全 5/5、TTFT 133.7-134.0s；KV 余量 +51.1% 但 **position 余量仅 7 token** → MODEL_POSITION_BOUNDARY，不作默认生产工作点） |
| **P0B spec-off A/B** | MAINTAIN_SPEC_ON：P32K 轴 spec-off 大胜（+12~39%）但 D565 −53% 否决；**spec 价值随 prompt 长度反转** → 条件路由发现（非配方变更） |
| K5 pos1 复议 | 维持 REJECTED（P32K speedup 0.788<1 独立否决）；地板规则方向感知修正建议（Phase 04+） |
| churn 稳态 | RETDEF 维持（显式 1024 无收益 + p95 +29%；亚压力稳态证据） |
| KVARN 0.28 参考 | 三档 needle 全 5/5（TTFT 98.9-112.0s）、KV 池 492K；CROSS_RUNTIME_REFERENCE 保留至 Phase 08 |
| SLO 状态 | **SLO_UNDECIDED 维持**（Erratum EP03-A2；p95 认证重跑见 §8） |
| TP1-C4 | 顺延（GPU2 外部任务全程占用 15h+；Debt 保持） |

## §1 P0A 契约落地

- **freeze fail-closed 重写**（用户契约 #1）：uv pip freeze + importlib.metadata 双路 PEP 503 规范化比对（199 包全一致）；rc/空输出/包数下限/关键包漂移全 FATAL；temp→校验→atomic rename。**EVIDENCE_REPAIR 非 ENV_DRIFT**（vllm tree `4632d624…`/2537 文件、patch-unit 18 件、台账、symbol provenance、7 关键包版本零漂移）；freeze 重写 sha `d6ee86e9…`（旧 0 字节 `e3b0c442…` 勘误留档）
- **SLO reconciliation**（#4）：Erratum 追加不改写历史；MANIFEST `slo_status` 保持 SLO_UNDECIDED
- **schema 1.3 + gates-phase03 冻结**：262K 双余量分账、四标签（PRODUCTION_SAFE/BOUNDARY_PROFILE/HARD_CEILING_CAPABILITY_PASS/UNSUPPORTED）、needle 配对判读（s99/s2/s5 冻结）、skip_layers 条件触发 bounded≤2、KVARN 三禁令
- **能力探针**：fp8/fp8_e4m3/fp8_e5m2 CLI 面 SUPPORTED；`kv_cache_dtype_skip_layers` 实名；Mamba recurrent state 独立 dtype（无 fp8）→ hybrid 分账实证；**FP8C 官方通路确认**（k/v_scale 为 checkpoint 参数 + CompressedTensorsKVCacheMethod + parent `kv_cache_scheme:null` 槽位）；**Debt #7 新出口**（`--cudagraph-metrics` + CUDAGraphStat：padded/unpadded/paddings/runtime_mode 聚合日志）；boot028 冻结配方全量回读
- **校准/评测物理隔离**（#3/#5）：独立合成语料 64 样本（sha `71b08a93…`，seed 20260921，非 ulmus filler 族）+ fixtures/eval/phase03-manifest.json + overlap checker **PASS**（15 needle 码零泄漏）；Docker+UV 构建环境就绪（fp8c-build 容器，llmcompressor 0.12.1a/compressed-tensors 0.18.0/torch 2.13.0+cu13）
- **fixture 扩表**：needle-p{238,245,262}k-s{99,2,5}-ph3 九档离线 tokenizer 装配验证全过——**新事实：chat 模板实测 +52 token → 262K 档 model position 余量仅 7 token**（238K 5467 / 245K 6151）；p245k/p262k 入 FIXTURE_TARGETS（262K=261888 装配公式）

## §2 P0B L2 终形（先于 KV 主矩阵完成）

- **P32K spec-off 正式 A/B（W0 + 3 轮 × 2 臂 back-to-back 认证形制）→ MAINTAIN_SPEC_ON**：
  P32K 轴 spec-off 大胜（decode +12.0%、aggregate +33.0%、冷 TTFT −36.4%、暖 TTFT −39.2%、TPOT −10.7%），**D565 控制轴 −53.3%**（85.2 vs 182.4 tok/s）超 5% 退步线否决。SPECON R2 慢态 boot（59.3 家族）被 spread 门逮住（15.3%）；两平台态下 P32K 方向一致（快态 +12%/慢态 +32%）——结论符号稳定。
  **结构性结论：spec 价值随 prompt 长度反转**（D565 2.13× 短提示优 / P32K 拖累：draft 32K prefill 罚 + verify 开销）→ L2 单一配方维持 spec-on；**P32K spec-off = 工作负载条件性路由发现**（进三档路由建议，非 composite 变更）
- NBT3072@P4K 免复验（终形未翻转；Phase 02 认证 +10.7% 继续有效）
- **K5 pos1 复议（纸面）**：pos1 抬升与总接受率抬升各位置同幅（+14.4/+12.8pp）= 截断选择均匀提升，非 pos 特异异常——规则本意（防塌缩）未被违反，对称 |gap| 判定正向误触发；但 K5 独立死于 P32K speedup_vs_tonly 0.788<1 → **维持 REJECTED**；方向感知修正作为 Phase 04+ 规则建议
- 事故与处置：双链重复发射（人为）——铁律 5 核验 PGID 杀年轻链 + 孤儿自亡确认；NAT238K --only 补偿

## §3 P1 KV 对决（四路 → 实测两路 + 引用）

- **FP8E4（scale=1.0 诊断臂）：UNSUPPORTED（boot 级三重取证）**——F8E4L32/F8E4X128/F8E4TRITON 诊断臂全部 rc=11；config 层通过（`Using fp8_e4m3…`、resolved `kv_cache_dtype=torch.float8_e4m3fn`、Marlin W4A16 正常），serving 层死于 flashinfer 0.6.18 fp8_e4m3 prefill 内核 **JIT ninja 编译**（自带 CCCL 头 × cu13 nvcc：`cuda_toolkit.h:41 #error`）；`VLLM_ATTENTION_BACKEND=TRITON_ATTN` env 不改变崩溃路径。**与 0.28 栈 FP8 UNSUPPORTED 同根因家族**（Phase 01 顺延预言证实）
- **FP8C（calibrated 生产候选）：UNSUPPORTED（同 serving 层阻断）**——calibrated scales 不改变内核编译；artifact 构建取消。隔离构建/验证链（Docker 容器 + build/verify 脚本 + 独立语料）就绪待上游修复（flashinfer ≥0.6.19 或 CCCL 修复）后 Phase 04+ 重开——**上游债留档**
- **NATIVE 0.29（主栈唯一 eligible）**：短档/日常档引用 Phase 02 认证 + P0B spec-on 终形；238K Screen 5/5（TTFT 116.4s）；238K/245K/262K 正式认证见 §4
- **KVARN 0.28（CROSS_RUNTIME_REFERENCE）**：见 §5
- **KV 对决减路说明**：MASTER §9 四路在 0.29 栈实测为 NATIVE 单路可服务；FP8 双路 UNSUPPORTED（证据三 boot）；KVARN 跨版本参考不参与 0.29 选型——Gate C 三档全部由 NATIVE 承担，偏差如实记录

## §4 238K/245K/262K 正式认证（双余量分账）——**全档通过**

3 boot × 3 seed（s99/s2/s5）单请求五针，共 27 格 **全 5/5**（`raw/staging/PH3-KV/certify-238plus-report.json` + CERT238P-* 证据目录）：

| 档 | model_len | workpoint | TTFT（min-max, s） | KV 池容量 | kv_capacity_margin | model_position_margin | 标签 |
|---|---|---|---|---|---|---|---|
| 238K | 243712 | 238,245 tok | 116.3–116.7 | 394,148 | **+65.4%** | 5,467 tok | **PRODUCTION_SAFE** |
| 245K | 251392 | 245,241 tok | 121.3–121.6 | 394,941 | **+61.0%** | 6,151 tok | **PRODUCTION_SAFE** |
| 262K | 262144 | 262,137 tok | 133.7–134.0 | 395,979 | **+51.1%** | **7 tok** | **HARD_CEILING_CAPABILITY_PASS** |

- preemptions=0、OOM=0（逐 boot 日志核查）；boot 间 TTFT 极稳（±0.2%）
- 262K = **MODEL_POSITION_BOUNDARY 主导**：KV 池尚余 51%，但 chat 模板实测 +52 token 使 position 窗口仅剩 **7 token**——按契约只标硬上限能力，**不作默认生产工作点**；极限生产安全档 = 238K/245K
- Phase 02 CEILING_OBSERVATION → 本认证转正；s2@238K/245K/262K 全 5/5（其已知失败域仅在 128K，码集×长度非正交再证）

## §5 KVARN 0.28 参考臂（CROSS_RUNTIME_REFERENCE）

`ph3_kvarn_ref`（boot028 冻结配方：max_model_len=245760 / kvarn_k4v2_g128 / block128 / spec k7，tp2 ms8）：

- **needle s99 三档全 5/5**：224K TTFT 98.9s / 238K 107.7s / 245K 112.0s（VRAM 峰 15.8GB/卡）
- D565-F512-C1 中位 **151.7 tok/s**（0.28 栈；跨版本不可与 0.29 数字直接比加速比）
- KV 池 492,266 tokens（vs 0.29 native 同形 ~394-396K）
- 262K = out_of_domain（超出 245760 冻结配方，非质量 FAIL，按契约标注）
- 三禁令遵守：无跨版本 winner 主张、无 tie-break 套用、无越域判定；**legacy/extreme reference 保留至 Phase 08 切换窗口**

## §6 churn 稳态 / 租户隔离（ph3_churn，Screen 级 A/B）

负载：持续 Poisson 1.2 rps P4K 主体 + 每 45s 一个 P32K 长插入 + 4 租户 2K-token 共享基座 + 每请求唯一尾；600s 稳态窗（seed 20260921 冻结）：

| 臂 | ok/req | TTFT p50/p95 | 短请求前后半段 p50 | KV 峰 | prefix hits/queries |
|---|---|---|---|---|---|
| RETDEF（默认） | 603/603 零错 | 0.211 / **0.275** | 0.223 / 0.210 | 17.8% | 2,478,592/2,955,181（83.9%） |
| RET1024（显式） | 603/603 零错 | 0.211 / **0.356** | 0.224 / 0.211 | 17.8% | 2,472,448/2,963,697（83.4%） |

- **判定：RETDEF 维持**——显式 retention 1024 无吞吐/命中收益且 p95 尾部 +29%（与 Phase 02 闭环测试的 warm 退步方向一致，churn 稳态下再证）
- 前后半段 TTFT 稳定（无暖衰减），双臂零错误/零抢占
- **证据边界（如实）**：KV 峰仅 17.8%——本负载未进入驱逐压力区，Phase 02 的 6.2× 存活观察所涉强驱逐形态未被本测覆盖；显式值在"亚压力稳态"下无收益+尾部代价已证，强压力区 retention 行为留 Phase 04+（非本相位门）
- 租户隔离/哈希碰撞：本 churn 负载双臂输出均正常（无跨租户内容串扰迹象——唯一尾逐请求不同）；正式租户隔离探针未单列（MASTER §9.1 行 477 项），随 Phase 04 真实 Agent 横评补

## §7 三档 Profile + Gate C（raw/staging/PH3-GATEC/gatec-verdict.json）

**Gate C 分档 verdict：short PASS ∧ daily PASS ∧ extreme PASS**（单 route UNSUPPORTED 不拖垮全局的规则生效：FP8 两路缺席由 NATIVE 承担）

| 档 | runtime + KV route | context envelope | 关键数 |
|---|---|---|---|
| **short（L2）** | 0.29 冻结栈 + NATIVE_BF16 + spec k7 + NBT2048 + MS4 | D565/P4K/P32K（model_len 36864） | D565 decode 182.4 tok/s；P32K decode 69.8 / 暖 TTFT 0.299s（3-boot 认证）；**条件路由：P32K 级负载 spec-off 更优（+12%/+33%/−39%）** |
| **daily（X2）** | 同栈（X2 形制）+ NATIVE_BF16 + q4 护栏 | 128K C1-C2（C4=CAPACITY_LIMIT 端点）/ 220K 在途=1 | Phase 02 Gate B：seed99 全档 5/5、220K TTFT −0.17%、容量 1.42×/1.78×；FP8 解锁落空（上游债） |
| **extreme** | 同栈（MS1 在途=1）+ NATIVE_BF16 | 238K/245K=PRODUCTION_SAFE；262K=HARD_CEILING 单列 | §4 全表 |

- **FP8E4/FP8C 分离结论**：FP8E4=诊断完成（三 boot UNSUPPORTED 取证）；FP8C=UNSUPPORTED（同一 serving 层 JIT 阻断，artifact 未构建，链路就绪待上游）
- **0.29 主栈正式选型 = NATIVE_BF16**（唯一 eligible）；KVARN 0.28 只作 reference 保留至 Phase 08

## §8 SLO 补点与 p95 认证重跑

- **D565 open p95 认证重跑（600s/点，68-311 样本/点 = Phase 02 的 1.1-5.2×）**：

| arrival (rps) | 0.0966 | 0.1932 | 0.2898 | 0.3477 (0.9×) | 0.4250 (1.1×) |
|---|---|---|---|---|---|
| served_ok | 68 | 149 | 223 | 240 | 311 |
| **ttft_p95 (s)** | 0.205 | 0.278 | 0.409 | 0.421 | **1.639** |

  **五点严格单调（Spearman ρ=1.0）；1.1× 过载点尾部 3.9× 陡升符合饱和行为（sat_est 0.3864）——Phase 02 报告的"D565 open p95 非单调"确证为 Screen 级小样本伪影**，遗留项闭合。范围注记：1-boot 认证窗口（boot2 按预算裁定跳过；跨 boot 复现归 Phase 04 SLO 定标）。
- **slo_status 维持 SLO_UNDECIDED**（无预冻结生产 SLO 数值 Authority；本节产出为定标曲线质量证据，非 SLO 裁决）
- KV duel 未解锁新并发档（FP8 UNSUPPORTED）→ X128-C4/X220-C2 维持 CAPACITY_LIMIT 端点记录，无 SLO 补点需求

## §9 六态归档（schema 1.3）+ Phase 04 Debt

| 方向/实验 | 实验六态 | route_eligibility | candidate_decision | capability_label | evidence_quality |
|---|---|---|---|---|---|
| P0A freeze 重审计 | VALID_PASS | — | EVIDENCE_REPAIR（EP03-A1） | — | COMPLETE |
| spec-off 认证 A/B | VALID_PASS | — | MAINTAIN_SPEC_ON（路由发现附注） | — | COMPLETE |
| K5 复议（纸面） | VALID_PASS | — | REJECTED 维持 | — | COMPLETE |
| F8E4L32 / F8E4X128 / F8E4TRITON | **UNSUPPORTED** | DIAGNOSTIC_ONLY | —（serving 层 JIT 阻断） | UNSUPPORTED | COMPLETE（三 boot 取证） |
| FP8C（构建取消） | NOT_RUN | — | UNSUPPORTED（同阻断；链路就绪待上游） | UNSUPPORTED | MEASUREMENT_NOT_AVAILABLE（构建层） |
| NAT238K Screen | VALID_PASS | ELIGIBLE | PASS（正式认证承接） | — | COMPLETE |
| certify-238plus 27 格 | VALID_PASS | ELIGIBLE | **PASS** | 238K/245K=PRODUCTION_SAFE；262K=HARD_CEILING_CAPABILITY_PASS | COMPLETE |
| KVARN 0.28 三点 | VALID_PASS | **CROSS_RUNTIME_REFERENCE** | —（保留至 Phase 08） | — | COMPLETE |
| churn A/B | VALID_PASS | — | RETDEF 维持 | — | COMPLETE（亚压力域注记） |
| D565 p95 认证重跑 | VALID_PASS | — | 见 §8 | — | COMPLETE |
| TP1-C4 | NOT_RUN | — | PENDING_SUPPLEMENT（GPU2 外占顺延） | — | MEASUREMENT_NOT_AVAILABLE |

**Phase 04 Debt（移交）**：
1. **TP1-C4 补测**（持续顺延——GPU2 外部任务占用贯穿本相位 15h+；gate-b PENDING_SUPPLEMENT 轴仍开）
2. **FP8-KV 上游解锁**：flashinfer ≥0.6.19 或 CCCL 头修复后重开 FP8E4/FP8C（probe→boot→KV-only 校准→单变量验证→Screen 链全部就绪：build/verify 脚本 + 独立语料 71b08a93… + fp8c-build 容器；解锁后 X128-C4（526K 工作点）/X220-C2 容量档重评）
3. **KV-only 校准语料/评测隔离机制**保留复用（Phase 04 量化矩阵直接继承）
4. **K5 地板规则方向感知修正**（规则建议已落档；Phase 04+ 采用）
5. **强驱逐区 churn/retention 行为**（本相位为亚压力稳态证据；需 KV 压力负载形态）
6. **租户隔离/哈希碰撞正式探针**（MASTER §9.1 行 477 项，随 Phase 04 真实 Agent 横评）
7. **graph-replay 计量**：`--cudagraph-metrics` 新出口（CUDAGraphStat：padded/unpadded/paddings/runtime_mode）可在 Phase 04 CG 相关臂启用，evidence_quality PARTIAL 可部分升级
8. **MS8-C8 吞吐档**（Phase 02 Debt #8 → Phase 04 拓扑赛复访）；**冷启动热机手册**（Phase 02 Debt #9 → Phase 08）
9. 238K+ 各档 SLO 双曲线端点（如生产需要可按 §7 Profile 卡扩展）

## §10 收口

- **Gate C 三档 PASS**：三档 Profile 卡见 §7；0.29 主栈 KV 正式选型 = NATIVE_BF16；KVARN 0.28 跨版本参考保留至 Phase 08 切换窗口（生产切换铁律 9 拍板制不变）
- **SLO_UNDECIDED 维持**（Erratum EP03-A2 口径；MANIFEST 单一 Authority 未变）
- 生产 GPU0/1 与 :8000 全程零触碰；GPU2 外部任务零干预；GPU5-7 零进程操作；自有 PGID 全清（含两起事故处置：双链重复、僵尸 server——铁律 5 核验后清理，NAT238K/churn 均补偿重跑）
- 证据全集：raw/staging/{PH3-P0B,PH3-KV,PH3-GATEC} + V29-T2-P0B-*/V29-T2-PH3-*/CERT238P-* + sandbox log-p02-f8e4*；repro 链 tools/{p0b_*,ph3_*,build_fp8c_*,verify_fp8c_*,gen_calibration_corpus,check_calib_eval_overlap}.py + ph3_master_gpu_chain.sh（断点续跑形制）

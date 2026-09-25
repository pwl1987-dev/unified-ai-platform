# Phase 06 报告：真实 Agent 公平横评（Gate F）

> 战役：nextgen-20260917 · Phase 06 · 状态：**完成（Gate F 三判定落定）**
> 冻结合同：`repro/gates-phase06.yaml` v1.0（commit d4188a9，任何正式 cell 之前冻结）
> 输入：`repro/topology-phase05/phase06-handoff.json`（Gate E 四冠军 + M4 冻结，未重开）
> 机器判定：`raw/staging/PH6-P4/gate-f-verdict.json`（schema 校验 PASS：16 场景 + 47 dual 快照）

## 0. 执行链与修复记录

| 步骤 | 状态 | 证据 |
|---|---|---|
| MIG-01 仓库迁移 | ✅ `pwl1987/qwen3.8-27b-8x4090-stack` → `pwl1987-dev/unified-ai-platform`（history 连续，双旧 URL 重定向验证） | `raw/staging/MIG-01/` |
| P0 合同冻结 + harness 自测 | ✅ 3×SELFTEST_PASS（router parity/role/evict + workload mock + gate 9 路径） | `raw/staging/PH6-P0/` |
| M4 臂（首轮） | ❌ 无效——persona 请求漏 `enable_thinking=False`（PH6-EVIDENCE-REPAIR-01，原证据全保留） | `raw/staging/PH6-P1-INVALID-THINKING/` |
| M4 臂（修复后重跑） | ✅ 8 场景全 rc=0（boot 唯一，r1 预热/r2 正式两轮交错） | `raw/staging/PH6-P1/` + `ph6-m4-arm-summary.json` |
| F3 T2 3-boot + T1 对照 | ✅ 4 臂 COMPLETE，verbatim 4/4 rc=0 | `raw/staging/PH6-P3/` + `ph6-f3-all-arms.json` |
| Gate F 机器判定 | ✅ F1=BLIND_SUFFICIENT / F2=ISOLATION_PASS / F3=CONFIRMED_DUAL_CHAMPION | `raw/staging/PH6-P4/gate-f-verdict.json` |

**PH6-EVIDENCE-REPAIR-01**：Qwen3.8 思考模板 +~45 token 使 p128kt 级请求 131073>131072 恰超 1 token（引擎 400×203）；修复=对齐 bench 全战役标准 body（`chat_template_kwargs.enable_thinking=false` + include_usage）+ CAPACITY_LIMIT 错误分类 + 每会话成败账。首轮 M4 证据整体作废保留，修复后全新重跑。

## 1. 范围界定（如实）

MTP §12 的 Agent **产品层**横评（Pi/Claude Code 等多客户端拉平对比）本机无第二 Agent 产品实例可拉平驱动，不在本窗口执行（合同 scope_note 冻结在案）；本 Phase 交付 **Agent 形态负载下的 infra 公平性**：角色路由（F1）、租户隔离/驱逐（F2）、T2 冠军跨 boot 资格（F3）。Agent 产品层横评移交 Phase 06b/07 前置。

## 2. F1 角色化路由 A/B（M4-Q0，同 boot 同负载）

设计：A_BLIND=ph6_router v1.1 parity（selftest 断言决策序列逐位一致）vs B_ROLE=role 池（short/batch→TP1 池，long→TP2；长度守卫仍强制）；同一 M4 boot 内两轮交错（r1 预热留档 / r2 正式判），同 seed/温度/语料/并发，传输头集逐字节一致（两臂同发 X-Role，blind 忽略）。

**正式轮（r2）per-role：**

| 轴 | A_BLIND | B_ROLE | 备注 |
|---|---|---|---|
| short P95 TTFT（主轴） | **0.9397s** | **0.9178s** | Δ2.3% 落 3% 带 → EQUIVALENT |
| short 完成率 | 12/12 | 12/12 | 均 1.0 |
| long 完成率（硬门） | 3/3 | 3/3 | 均 1.0 |
| batch goodput | 1795 tok/33.4s | 1894 tok/21.1s（**+6.5%**） | 改善不计回退 |
| placement audit | — | **100%**（354/354，short/batch→TP1*，long→TP2） | B 有效执行成立 |

**机器判定：F1 = BLIND_SUFFICIENT**（全部轴 EQUIVALENT——更简单 router 胜出；M4 生产不带角色层即可守住短交互保护）。

次要观察（不入判定，如实双列）：role 轮 long P50/P95 0.29/0.55s vs blind 11.3/11.6s——blind 下 p32k 长会话可被 least-inflight 落到 TP1 且跨轮前缀局部性不保证，role 池+粘滞给出确定性缓存局部性；连带 fairness jain 0.990 vs 0.717、aggregate 266 vs 90 tok/s。结论分层：**角色路由对"短尾保护"非必要（F1 主判定），对长会话缓存局部性/公平性/聚合吞吐有实质收益（观察级，建议 M4 生产开启 role 池以获得确定性局部性——交 Phase 07 决策，不回改 F1 判定）**。

## 3. F2 租户隔离 / churn / 强驱逐（M4，role 策略 + blind 对照）

场景：2×p128kt 连续 hog（len-guard 强制落 TP2，MS2 双槽常占）+ 3×d565 常驻 short + 6 波×20s churn short；t=60s 经 `router /admin/evict` 强驱逐 hog-1。

**硬门 10/10 全过（机器判定：F2 = ISOLATION_PASS）：**

| 硬门 | 实测 | 门限 |
|---|---|---|
| short P95 TTFT | **0.5117s** | ≤5.0s |
| short 完成率 | 36/36 = 1.0 | =1.0 |
| long 完成率（驱逐家族单列后） | (30 ok + 59 EVICTED + 1 EVICTED_MIDSTREAM)/90 = 1.0 | =1.0 |
| jain_short goodput | **0.9272** | ≥0.90 |
| failure window（short TTFT>5s 连续窗） | **0.0s** | =0 |
| churn 6/6 波全完成 | ✓ | 全完成 |
| 会话地图无泄漏（inflight 归零） | ✓（三 backend 全 0） | 无泄漏 |
| 强驱逐：被逐会话明确错误 | ✓（在途 409 SESSION_EVICTED；中途截断 1 例 EVICTED_MIDSTREAM 如实分类） | 不挂起 |
| 驱逐→TP2 可服务 release latency | **0.9494s**（探测请求 TTFT） | ≤15s |
| router 存活 + probe ok | ✓ | 存活 |

对照量化：blind 策略同场景 short P95 0.5114s / fw 0 / 完成 1.0（两策略等价守住）；**饿死基线 PH5 mixed-T2 50.44s → M4 0.51s（降 98.7%）**——M4 拓扑本身（TP1 池 + len-guard）即构成 bulkhead，路由策略二选一皆守底线。驱逐机制（v2.0 独有）代价：宽限窗 60s 内被逐会话 409、驱逐后即释放。

## 4. F3 T2 双 Agent 冠军 3-boot 资格补足

形制：ph5_boot + ph5_router v1.1 + ph5_workload multi 逐字同源（同 experiment-id=同 prompt/salt）；每 boot R1=冷前缀（PH5 每 boot 单次执行同形制——Gate E 参考值即此形制；R2/R3 为同 prompt 前缀缓存热化观测，不入判定）。T1-B04 漂移对照先行校验。

| boot | dual_p32k per-session tok/s（R1 冷） | warm R2/R3（观测） |
|---|---|---|
| T2-B01 | 17.432 / 17.440（boot 中位 **17.436**） | 59.2 / 58.7 |
| T2-B02 | 17.397 / 17.390（**17.394**） | 59.0 / 59.4 |
| T2-B03 | 16.841 / 17.324（**17.083**） | 53.5 / 59.4 |
| T1-B04（对照） | 15.038 / 15.426（**15.232**；vs PH5-P3 参考 15.249，**漂移 -0.11%** ≤3% → 可比成立） | — |

**机器判定：F3 = CONFIRMED_DUAL_CHAMPION**——T2 3-boot 中位 **17.394** ≥ T1 参考 15.249 **+14.07%**（出 3% 带）∧ 逐 boot 方向一致 3/3 ∧ 跨 boot 极差 2.1%。Phase 05 screen 级资格正式补足为 3-boot 认证。辅助发现：同 prompt 前缀缓存稳态 ~53-59 tok/s/会话（冷形制 3.3×）——多轮 Agent 会话的缓存红利量化入档。

## 5. Gate F 汇总

| 问题 | 判定 | 一句话 |
|---|---|---|
| F1 角色化路由是否 M4 生产必要 | **BLIND_SUFFICIENT** | 短尾保护两臂等价；更简单 router 胜出（角色层对缓存局部性/公平性的增益记观察级建议） |
| F2 租户隔离/驱逐是否守住公平底线 | **ISOLATION_PASS** | 10/10 硬门全过；M4 对 T2 饿死基线降 98.7%；驱逐机制干净（release 0.95s） |
| F3 T2 双 Agent 冠军跨 boot 资格 | **CONFIRMED_DUAL_CHAMPION** | +14.1% 出带、3/3 boot 同向、漂移 -0.11%；3-boot 资格补足 |

## 6. 结论与去向

1. **M4 生产化前提达成**：短交互保护与租户隔离在 M4 上以 v1.1 语义即成立；角色化路由端点降级为"可选增强"（收益=长会话缓存局部性 jain 0.99/agg 266 vs 0.72/90）——Phase 07 生产装配时按需启用 ph6_router v2.0 role 池与 /admin/evict。
2. **T2=双 Agent 冠军升级 3-boot 认证**（17.39 tok/s/session），handoff 数字更新。
3. **prefix-cache 稳态 3.3×** 冷形制（dual 会话）——Agent 多轮工作负载的部署级红利，Phase 07 长稳混合流量设计输入。
4. 遗留：Agent 产品层横评（MTP §12 全量）→ Phase 06b/07；M4-COMPOSED（batch→Q4C backend）账本已建未执行（合同 ARM-C，时间盒外）。
5. 下一 Phase handoff：`repro/agent-phase06/phase07-handoff.json`。

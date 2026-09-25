# Phase 05 报告 — 四卡拓扑赛 → Gate E（nextgen-20260917）

- 计划：用户 2026-09-25 执行合同（连续推进至 Gate E）；gates-phase05.yaml（sha `edf06709…`，看结果前冻结）
- 输入：repro/quant-phase04/phase05-handoff.json（PH4-EVIDENCE-REPAIR-01 修复后 2 Q-Profile；Q1M=reference only）
- 环境：runtime029 只读（tree `4632d624…`）；KV=NATIVE_BF16 全程；Q0 anchor 同 artifact；250W 墙
- 授权卡：GPU2/3/4/6（GPU2 于 08:0x rpg-bakeoff 退出后并入）；GPU0/1/:8000 生产零触碰；GPU5/7 外围零触碰
- Router：ph5_router.py v1.1（sticky-session + least-inflight + 长度守卫 + failover；SELFTEST_PASS 六断言）
- 事故全留痕：见 §7

## §0 结论速览（Gate E 四冠军；screen=1-boot×3-reps，qualify=T1/T3/T4×3-boot 中位）

| 冠军类 | 胜者 | 依据（对最接近者） | 证据级 |
|---|---|---|---|
| **Throughput Champion** | **T1=4×TP1** | d565-C16 goodput 2.01 rps vs T3 0.81（2.5×）；p4k-C4 268 tok/s vs T3 181（+48%）；p4k-C16 1.67 vs 1.17 rps | screen+qualify |
| **Single-Agent Champion** | **T4=TP4** | 三轴全胜 T2：d565 204.1（+10.2%）/p32k 72.5（+7.7%）/p128k 19.6（+5.9%）；P220K 单会话独占可服务 | screen+qualify |
| **Dual-Agent Champion** | **T2=2×TP2**（screen 级） | per-session decode 17.1 vs T1 15.0（+13.6% 出带）；jain 0.9996 | screen（1-boot 标注） |
| **Mixed-Production Champion** | **T3=TP2+TP1+TP1** | 守门轴唯一通过：短 P95 TTFT 0.27s vs T2 50.4s / T4 63.4s（同构拓扑短请求被 130K prefill 饿死）；aggregate 28.3 并列最高 | screen+qualify |

**M4 判定**：T3 在真实 mixed workload 守门+aggregate 双成立 → **M4 = TP2 + TP1 + TP1 冻结**（gates m4_freeze_rule 触发条件满足）。

**TP4 保留判定**：early-stop 三轴全胜 CONTINUE + P220K 实证 + 单Agent 冠军 → 保留（非仅理论 KV pool）。

## §1 拓扑与统一因子

- T1=4×TP1@36864/MS4/spec-k7（吞吐候选）；T2=2×TP2@131072/MS2（双交互）；T3=TP2@131072+2×TP1@36864（通用生产）；T4=TP4@262144/MS2（极端单会话）
- 统一：Q0 同 artifact/同 router v1.1/同 client/同采样/同 fixture/250W 墙；direct 与 through-router 双轨
- 卡位映射：T2=对(3,4)+(2,6)；T3=TP2(3,4)+TP1(2)+TP1(6)；T1=TP1×(2,3,4,6)；T4=TP4(2,3,4,6)
- Router v1.1：X-Session-Id sticky + least-inflight + **长度守卫**（est_tokens vs backend max_len；T3/M4 混合拓扑必需——P128K 禁入 36864 backend）+ 1s 健康探测 3 败摘除 2 胜回池

## §2 关键数字矩阵（screen 级中位；P3 qualify 中位见 §4）

| 轴 | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| d565-C1 decode tok/s | 141.5 | 185.1 | 175.3 | **204.1** |
| p32k-C1 decode | 60.8 | 67.3 | 68.8 | **72.5** |
| p128kt-C1 decode | CAP_LIMIT | 18.5 | 18.5 | **19.6** |
| p220k-C1 | CAP_LIMIT | CAP_LIMIT | CAP_LIMIT | **可服务（独占）** |
| d565-C16 goodput rps | **2.01** | 0.47 | 0.81 | 0.23 |
| p4k-C4 agg tok/s | **268.0** | 155.5 | 181.0 | 102.5 |
| p4k-C16 goodput | **1.67** | 0.79 | 1.17 | 0.57 |
| dual 2×P32K per-sess | 15.0 | **17.1** | 5.2 | 10.1 |
| dual 2×P128KT per-sess | — | **2.15** | 1.38 | 1.39 |
| four 4×P32K aggregate | **58.5** | 39.3 | 47.3 | 19.8 |
| mixed 短 P95 TTFT | —（长不可服务） | 50.4s ✗ | **0.27s ✓** | 63.4s ✗ |
| mixed aggregate | — | 27.9 | **28.3** | 24.6 |
| CAPACITY_LIMIT 确定性 | p128k/p220k/mixed | p220k | p220k | failover N/A（单 backend） |

## §3 机制发现

1. **TP4 单流收益真实**：spec-decode 接受率/带宽随 TP 宽度提升——d565 +10.2% 非 KV pool 理论值；262K@TP4 boot 稳定（4×23.3GB）。
2. **同构拓扑的混合饿死**：T2/T4 的 mixed 中短请求 P95 TTFT 50-63s（排队于 130K prefill 后）；T3 异构分流后 0.27s——**异构拓扑的生存价值由守门轴实证**。
3. **TP1 吞吐王**：4×MS4=16 槽位 vs T3 10 槽 vs T2 4 槽 vs T4 2 槽——批处理 goodput 与槽位数强相关；T1 p4kC4 268 tok/s 为全部拓扑最高单 cell 聚合。
4. **Router 开销噪声级**：direct vs through-router 差 <0.1%（d565 C1 三拓扑一致）——v1.1 asyncio 代理不构成瓶颈。
5. **Failover 代价**（3 卡 preflight + 各臂）：3×1s 探测窗口内绑定会话失败（T2 4 run 失败）→ 2.3s 重绑/回池恢复；one-shot 新会话流量无感（避开死 backend）。
6. **长度守卫必要性**：无守卫时 P128K 会 400 于 36864 backend（est 保守估计 111581>36864 正确拦截；估计器对非 CJK 内容低估记录在案，p128kt vs 36864 分离度 3.5× 安全）。

## §4 P3 Qualify（T1/T3/T4 × 3 boots B01-B03，全臂含 verbatim canary；12:28-16:41）

- **verbatim canary 9/9 boots 全过**（100 行逐位）；9 臂 rc=0
- **跨 boot 漂移（d565-C1 直轨中位）**：T1=144.0/144.0/144.0（**0.0%**）｜T3=175.3/175.5/177.8（1.4%）｜T4=203.3/203.5/203.9（0.3%）——全部 ≪3% 带，四冠军判定鲁棒
- 3-boot 中位关键值（vs screen 修正）：T3 dual-P32K per-session 5.2→**15.2**（screen 离群被多 boot 中位吸收，会话双落 TP1 的偶发路由）；T1 p4k-C4 agg 268→255.7；T4 d565 203.5/p32k 72.4/p128k 19.6——冠军归属无一翻转
- **T3 路由特性记录**：无 session 标签的 C1 请求经 router 按 least-inflight+名字序默认落 TP1 backend（d565_c1_router T3=144.0 vs direct 175.5）——异构拓扑生产部署须带会话标签或角色化路由（Phase 06 建议项）
- 双 Agent 冠军证据级说明：T2 为 screen 单 boot（3 reps，+12.1% vs T1/T3 出带；未入 P3 名额，如实标注）

## §5 Debt 清偿

- **MS8-C8**（Phase 02 #8）：TP1@MS8 D565-C8 三 rep——aggregate 232.2 tok/s、max_running 5（DO_NOW 清偿）
- **TP1-C4**（Phase 02）：=T1F P4K-C4 direct 78.0 tok/s（并入 T1 直轨清偿）
- FP8-KV：DEFERRED_CONDITIONAL 维持；租户隔离/churn：Phase06；graph-replay：未启用；K5：CLOSED；SLO238+：DEFERRED

## §6 Gate E 终判（raw/staging/PH5-P4/gate-e-verdict.json，机器判定）

| 冠军类 | 判定 | primary 轴值（中位） | 次名与边距 |
|---|---|---|---|
| Throughput | **T1** | d565-C16 goodput 1.995 rps | T3 0.812（T1 = 2.5×）|
| Single-Agent | **T4** | 胜场 3/3（d565 203.5/p32k 72.4/p128k 19.6） | T2 次名，边距 +9.9%/+7.5%/+5.7% 全出带 |
| Dual-Agent | **T2** | per-session decode 17.09 | T1 15.25/T3 15.21（+12.1% 出带；screen 级标注） |
| Mixed-Production | **T3** | 守门轴唯一 TRUE（短 P95 0.27s） | T2/T4 守门 FALSE（50.4s/58.8s 饿死）|

- **M4 冻结**：mixed champion==T3 → **M4 = TP2 + TP1 + TP1**（TP2@131072 承长上下文/交互 + 2×TP1@36864 承短/批）
- **TP4 保留**：Single-Agent 冠军 + P220K 独占可服务 + early-stop 三轴全胜
- **T2**：Dual-Agent 冠军（screen 级）；mixed 守门失败与吞吐劣势如实记录——生产角色=双长会话低延迟档
- **T1**：纯吞吐档（16 槽位）；单流最弱（141-144）与长上下文不可服务为边界
- **CAPACITY_LIMIT/UNSUPPORTED 清单**：T1={p128k,p220k,mixed-long,T1L(TP1@131072 引擎数学拒绝 9.05>4.8GiB)}；T2/T3={p220k}；T4={failover(单 backend N/A)}；T2 failover=4 run 失败窗口+2.3s 重绑
- **Router 开销**：direct vs through-router <0.1%（三拓扑 C1 一致）→ 不构成选型因素

## §7 事故与修复全留痕

1. p128kt mt=256 超装配预算全 400（PH4 认证实参=mt=128；重跑三 rep）
2. pgrep -f 自匹配死锁×2（陈旧 wrapper 阻塞 followup 等待循环）
3. `cd && setsid &` 整链后台化 cwd 陷阱×2（绝对路径修正）
4. router 轨 thermal 门向 router /metrics 索要 vllm 指标 rc=20（--thermal-api 修）
5. RLOG 作用域 NameError（workload_cell 参数化）
6. **僵尸 router**（setsid 包装使 killpg 杀 wrapper 不杀 python）占 19710 → T1 场景段穿透污染作废重测；router 直启+启动验证修
7. **僵尸 v1 编排器** tag 碰撞：2100s 超时 finally 按名 kill 掉 v3 臂 backends（10:43 事故；其后 cell 重测）
8. 热积累 rc=20×2（T3 C8/C16-L004K；补测通过）
9. 四 cell argparse append 重复旗标；failover 时间戳窗口过滤
10. 外部 docs 提交者并行 push ×2（rebase 处置；main 非单写入实况记录）

## §8 收口

- 生产切换：铁律 9——本相位=拓扑 profile 候选，Phase 08 窗口拍板
- Phase06 handoff：见 repro/topology-phase05/phase06-handoff.json

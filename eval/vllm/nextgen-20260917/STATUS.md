# STATUS — nextgen-20260917 战役执行状态

> 本文件是执行状态跟踪，不替代仓库 Roadmap/Authority。最终结论回写 docs/VLLM-OPTIMIZATION.md。

- **Phase**: 01（KV 因果裁决 + 0.29 资格认证，计划 v1.2）— **执行中**
- **Last Completed**: Phase 00 全量（2026-09-17，commit #1=80e7d15 / #2=899eb5a）
- **Current Task**: P0 引导（MANIFEST v2 + schema 1.1 + gates 冻结 + 0.29 环境已建：vllm 0.29.0@g98dff2a81，能力探针完成，CLI 差异=--kv-cache-memory→--kv-cache-memory-bytes + help 分组制）
- **Next Task**: P1 KV 因果 A/B（0.28 栈 2×2 屏蔽 → 3-boot 矩阵）→ P2/P3 Layer A/B → P4 Layer X/C → P5 Gate A-S/A-X → P6 收口

## Phase 00 结论速览（详见 reports/phase-00-baseline.md）

| 块 | 结果 |
|---|---|
| 四锚点 | 2 项历史口径错误作废重定基线；今日同形制 spread 全 ≤1%（高度一致） |
| D1 compile-cache | DEBT1_PASS（结构/输出/性能三重确定性） |
| D2 238K 双 Gate | 正确性 FAIL：≥220K 浅层（0.1/0.3/0.5 位）needle 召回 2/5 确定性失败 ×3 复现；infra 稳定 |
| SLO | SLO_UNDECIDED 维持 |

## Harness Gate 检查单（§6.0 六条 + v2.1 增补）

| # | 条目 | 状态 |
|---|---|---|
| 1 | bench 指标口径修正（e2e/client_observed_decode/TPOT 分栏） | ✅ bench_nextgen.py |
| 2 | METRICS-SCHEMA.md + JSON Schema + 合成时间戳单测 | ✅ SYNTHTEST_PASS |
| 3 | TP1/TP2 完全相同 input/output token/stop/seed/采样 + 配对检查器 | ✅ pairing_check.py（锚点时实跑） |
| 4 | GPU UUID↔PID↔PCI BDF↔逻辑 index 关联自检 | ✅ nvml_bind.py（preflight 实跑） |
| 5 | 每次运行五件套落盘（client raw events/server log/metrics snapshot/进程-UUID 映射/退出码） | ✅ bench_nextgen 落盘 |
| 6 | verbatim 夹具负例检测（缺首行/缺末行/乱序/编号/复读） | ✅ SELFTEST_PASS |
| 7 | 流协议故障注入（partial/dup/missing-DONE/close/timeout/500/malformed） | ✅ FAULTTEST_PASS |
| 8 | TTFB 与 TTFT 分记（first_byte/first_header） | ✅ 事件层分记 |
| 9 | streaming/non-streaming token 计数 vs server usage 交叉核对 | ✅ instrument_selfcheck.py（首次 boot 后实跑） |
| 10 | 采样器统计（requested/actual interval/missing ratio/max gap/exit code） | ✅ 双采样器 |
| 11 | fixed-output 完整性断言（requested==completion==512，早停单列） | ✅ |
| 12 | stale-staging 恢复扫描 | ✅ classify.py scan-staging |

分类状态机演练：TEST-DUMMY 合规数据→VALID_PASS；缺必填字段→INVALID/SCHEMA_FAIL。
classify 端到端双向验证通过（2026-09-17）。

## 事件日志

- 2026-09-17: 目录树建立；MANIFEST.yaml 冻结物理卡位（TP1=GPU2/0E:00.0，TP2=GPU3+4/11:00.0+16:00.0）；功耗墙勘误决策=冻结 250W（MASTER §6.1 "450W" 与现场不符，历史无修改记录）；历史锚点参数提取（P32K C4: mt256/pt32768 natural-stop 197.5；P220K: mt128 TTFT 96.212s）。
- 2026-09-17: 审计发现历史 "P32K C4 197.5" 实为 D565 提示词（bench_conc 第 6 参缺省）→ 真形制 C4-L0565 重定基线 168.51；真 P32K C4 为抢占震荡区（agg 3.5–7.4，max_run=3）。P220K TTFT 重定基线 104.546s（历史 96.212 出处带伤不可比；warm 重放 1.18s 证前缀缓存有效；采样器税 <0.1%、争用排除）。
- 2026-09-17: D565 F512 双侧配对基线 131.581/172.832（spread ≤0.18%，pairing PASS）。
- 2026-09-17: D1 DEBT1_PASS（3 组冷建 2522 文件/组全同、探针哈希 3/3 一致、复用 boot 315s→45-55s、组内漂移 ≤0.3%）。勘误：Triton 冷证明快照路径笔误（~/.cache/triton vs ~/.triton/cache），以 mtime 实证补偿（构建窗口零写入）。
- 2026-09-17: D2 正确性 FAIL——238K/220K needle 均 2/5 ×3（丢浅层 0.1/0.3/0.5 位，S2 满中；temp=0 确定性）；infra 稳定（TTFT 漂移 0.03%、VRAM 恒定、零抢占）。执行勘误：stop() ps--pgid bug 致 b1 僵尸、b2/b3 未真 boot，跨 boot 稳定性降级为 within-server repeat（正确性结论不受影响）；stop() 已改 os.killpg。
- 2026-09-17: 流程事故链留痕：Desktop agent 层重启 4 次收割后台 runner（SSH 传输层 648 心跳零间隙，非网络问题；setsid/systemd-run 均被清理）；对策=断点续跑+前台分步+即时落盘；原 9 点位 D1 探针丢失，按"每组复用态 1 针"补扫。六态归档收口：valid 47 / invalid 10 / staging 0。
- 2026-09-17: push 收口——首次 push 遇远端新 5 个 docs 提交（rebase 干净）后 GH001：4 个未压缩 sampler-metrics.jsonl（105.66/99.55/99.05/90.36 MB）存于 12 提交栈中间历史（gzip 仅存在于最终树）。处置：`git reset --soft 80e7d15` 将其上 11 提交压为单提交，重跑脱敏扫描零命中、push 范围 >50MB blob=0，fast-forward 推送成功。**定稿 SHA：commit #1 = 80e7d15（harness freeze），commit #2 = 899eb5a（Phase 00 全量结果）**。勘误：各 manifest `harness_git_sha` 为运行时 HEAD 快照（5 个不同 pre-rebase SHA，rebase 后成孤儿）——**harness 权威指针以 commit #1 80e7d15 为准**。scoped cleanup 终验：GPU2/3/4=18 MiB 空闲、19701/19702 无监听、登记 PID 全退、GPU5-7 未触碰；生产 :8000 只读 health=200。
- 2026-09-18: Phase 01 P0 收口并推送（460fa8f）：MANIFEST v2（phase01 块）、schema 1.1（+CAPACITY_LIMIT、+candidate_decision 四层状态）、gates-phase01.yaml 全数值化冻结、vllm29-env 建立（0.29.0@g98dff2a81=官方 release commit，tree sha 45c5c919…，torch 2.13.0+cu130）、能力探针（**--kv-cache-memory→--kv-cache-memory-bytes 改名**；bfloat16 显式可选；turboquant_* 上游族在）、补丁五单元台账（unit-a 已移植 0.29 并 import 验证）。
- 2026-09-18: **P1 因果裁决（重大反转）**——2×2 屏蔽四臂全 2/5（kvarn/bf16 × target-only/spec），bf16 与 kvarn 输出逐字节一致；判别探针 seed99@220K 双 dtype 5/5、seed2 5/5、**seed1@128K 同败**→ ≥220K 召回失败为码集（夹具内容）依赖，**与 KV dtype/spec/长度均无因果**，DECISIONS #6 归因勘误、≥200K 质量冻结令解除。附带：bf16@220K 容量可行（2.03×）但 TTFT +7.7%；fp8 在 0.28 栈 UNSUPPORTED（flashinfer CCCL JIT 环境限制，双后端尝试皆死），FP8_DIAGNOSTIC 顺延 0.29。runner 勘误：stage2 dtype 映射 bug（臂标签误传 serve）已修。

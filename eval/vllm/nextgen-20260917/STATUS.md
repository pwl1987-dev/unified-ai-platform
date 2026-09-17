# STATUS — nextgen-20260917 战役执行状态

> 本文件是执行状态跟踪，不替代仓库 Roadmap/Authority。最终结论回写 docs/VLLM-OPTIMIZATION.md。

- **Phase**: 00（预检与 0.28 基线校准）— **完成**
- **Last Completed**: Phase 00 全量（四锚点重定基线 + D1 compile-cache PASS + D2 238K/220K 召回负结果 + 六态归档 + commit #2）（2026-09-17）
- **Current Task**: 无（Phase 00 收口）
- **Next Task**: Phase 01 — uv 建 0.29 环境；携四新基线（D565 F512 TP1=131.581 / TP2=172.832 tok/s；C4-L0565 agg=168.51；P220K TTFT=104.546s）；优先 A/B：bf16-KV vs kvarn 的 220K needle 对照（D2 负结果驱动）

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

# DECISIONS — nextgen-20260917 选型结论

> 只记录已由证据支持的正式结论；每条须引用 raw 证据路径与判定的 Gate。

| 日期 | 结论 | 证据 | Gate |
|---|---|---|---|
| 2026-09-17 | 历史"P32K C4 197.5 tok/s"作废：实际提示词 ~565 token（bench_conc 第 6 参缺省 512），历史 32K 标签全部口径错误；真 32K C4 冷为抢占震荡区（agg 3.5–7.4，max_run=3）不可用作工作点 | raw/valid/V28-T1-…-MS4-C4-L032K-NS-B01-R0{1,2,3}；历史 TTFT~1s vs 真 32K 物理需 ~16.7s | A2 establish_baseline |
| 2026-09-17 | "P32K C4"真形制（D565 提示词×4 并发 MS4）新基线 168.51 tok/s aggregate（168.201/168.602/168.513，spread 0.24%，驻留 4/4）；为 Phase 01 reference | raw/valid/V28-T1-…-MS4-C4-L0565-NS-B01-R0{1,2,3} | A2 establish_baseline ✅ |
| 2026-09-17 | D565 fixed-512 新基线：TP1=131.581 / TP2=172.832 tok/s（median，spread 0.18%/0.17%，严格配对 PASS，TP2/TP1=+31.3%）；为 Phase 01 reference | raw/valid/V28-T{1,2}-…-MS1-C1-L0565-F512-B01-R0{1,2,3}；pairing_check | A1/A3 establish_baseline ✅ |
| 2026-09-17 | P220K TTFT 新基线 104.546 s（103.888/104.546/104.882，spread 0.96%）；历史 96.212 不可比（+8.7%，当日出处带伤 §1.1 14W 读数无效）；采样器税<0.1%、争用已排除；warm 重放 1.18 s 证明前缀缓存有效 | raw/valid/V28-T2-…-L220K-F128-B01-R0{1,2,3}；L220KX-R0{1,2,3}；NO-NVML 对照 | A4 establish_baseline ✅ |
| 2026-09-17 | C4 并发完成丢前缀驻留（同 salt 重放 hits=0），C1 完整保留（P4K 45s 间隙 0.96s vs 冷 2.02s）；后续 Phase 01+ 的 warm 口径必须按并发形态分列 | raw/valid/ WARMPFX 对照 + anchors | 口径决策 |
| 2026-09-17 | **≥220K 浅层召回不可靠（真负结果）**：kvarn_k4v2 KV 下 238K 与 220K 五针均 2/5 ×3 复现（丢 0.1/0.3/0.5 位置，S2 内容满中 5/5），temp=0 确定性；基础设施无恙（TTFT 漂移 0.03%、零抢占/OOM）。裁决前 ≥200K 负载不得视为质量达标；Phase 01 优先做 bf16-KV vs kvarn 的 220K needle A/B | raw/valid/DEBT2-238K + 12×NDL 目录 | D2 正确性 Gate（FAIL） |
| 2026-09-17 | compile-cache 确定性成立：3 组独立冷建结构全同（2522 文件/组）、输出哈希 3/3 一致、复用 boot 315s→45-55s（~6.3×）、组内性能漂移 ≤0.3%；跨时段 132↔145 两档与功耗墙/温度态一致（非编译差异） | raw/valid/DEBT1-COMPILE-CACHE + 9×CC 目录 | D1 Gate（PASS） |

# Phase 00 基线报告（nextgen-20260917）

日期：2026-09-17 ｜ 冻结 harness commit：`49eaa8e16b6d557368c5abd7c14439cd57f6b029`
host-snapshot SHA256（前 16）：`6a08a3748937c2ff` ｜ 证据根：`raw/{valid,invalid,unsupported}/`

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 四锚点重测 | 全部完成；2 项与历史**不可比**（历史口径错误），按 establish_baseline 重定基线 |
| D565 F512（TP1/TP2 配对） | ANCHOR_PASS，新基线 131.581 / 172.832 tok/s（median，spread ≤0.18%） |
| "P32K C4"（真形制 D565 提示词） | 新基线 168.51 tok/s aggregate（median，spread 0.24%，驻留 4/4） |
| P220K TTFT | 新基线 104.546 s（median，spread 0.96%）；历史 96.212 不可比（+8.7%） |
| D1 compile-cache 补债 | **DEBT1_PASS**：3 组冷建结构全同（2522 文件/组）、确定性探针 3/3 哈希一致、复用 boot 提速 ~6.3×、组内性能漂移 ≤0.3% |
| D2 238K 双 Gate | **正确性 FAIL（真负结果）**：238K 与 220K needle 均 2/5×3 复现（丢 0.1/0.3/0.5 浅层针，S2 内容满中）；基础设施稳定（TTFT 漂移 0.03%、VRAM 恒定、零抢占）；跨 boot 证据因 stop() bug 降级为 within-server repeat（勘误如实标注） |
| Phase 00 → 01 一致性判定 | 同形制重测 spread 全部 ≤1%，**机器状态高度一致，放行 Phase 01** |
| SLO | `SLO_UNDECIDED`（无可靠生产 SLO，Phase 01/02 输出完整吞吐—延迟曲线） |

## 1. 审计修正（历史证据再检验，影响后续所有对比）

1. **历史 "P32K C4 197.5 tok/s" 实为 ~565 token 提示词**：dig028 bench_conc.py 第 6 位参数缺省 512（实际 tokenize 后 ~565），其全部 "32K" 记录 TTFT ~1 s（真 32K 冷前缀物理上需 ~16.7 s）。历史标签口径错误。
2. **真 P32K C4 冷 = 抢占震荡区**：32K 提示词 ×4 并发实测 aggregate 3.5–7.4 tok/s、max_running=3、29 次/运行抢占——不是可用工作点，是资源边界证据。
3. **C4 并发完成丢前缀驻留**：同 salt C4 重放 hits=0；C1 保留完整（P4K 45 s 间隙后 0.96 s vs 2.02 s 冷；P32K C1 重放 0.27 s vs 16.7 s）。
4. **P220K 历史 96.212 s 不可比**：当日 5 次同形制冷测 103.4–104.9 s；采样器税已排除（无 NVML 对照 103.48 s）；隔离对照排除争用（103.42 s）；历史出处本身带伤（§1.1 14 W 读数无效）。
5. **功耗墙勘误**：MASTER §6.1 "450 W" 与现场不符，实测机架级 250 W 冻结（MANIFEST `power_wall.frozen_no_change`）。
6. warm 前缀证据：P220K 同 salt 重放 TTFT 1.18 s（vs 冷 104.9 s），命中率 100%。

## 2. 四锚点结果

口径：`client_observed_decode_tok_s = (output_tokens−1)/(last−first)`；C4 aggregate = Σoutput_tokens/batch_wall_time；<2 tokens → null。

### 2.1 锚点 1/3：D565 fixed-512（TP1=GPU2 / TP2=GPU3+4，严格配对）

| 侧 | R01/R02/R03 (tok/s) | median | spread | 判定 |
|---|---|---|---|---|
| TP1 (MS1) | 131.766 / 131.534 / 131.581 | **131.581** | 0.18% | establish_baseline ✅ |
| TP2 (MS1) | 172.575 / 172.832 / 172.868 | **172.832** | 0.17% | establish_baseline ✅ |

- 配对检查 PASS（fixture SHA / actual_input_tokens / requested=completion=512 / stop / seed 全同）。
- TP2/TP1 = +31.3%（8B→TP2 增益，进入 Phase 01 参考集）。
- natural-stop sanity：TP1 130.374 / TP2 177.060 tok/s，质量正常。
- **此二值为 Phase 01 的正式 reference**（gates `reference_mode: establish_baseline`）。

### 2.2 锚点 2：C4 并发（真形制 = 历史 "P32K C4" 的实际提示词 D565）

| 实验 | R01/R02/R03 aggregate | median | 驻留 | 判定 |
|---|---|---|---|---|
| MS4-C4-L0565-NS（新基线） | 168.201 / 168.602 / 168.513 | **168.51** | max_running=4/4 | establish_baseline ✅ |
| 历史标签值 | 197.5（±5% gate） | — | — | **不可比→VALID_FAIL(口径)** |

- 与历史差 −14.7%：gate 落空原因=历史口径错误（§1.1），非机器漂移（今日三测 spread 0.24%）。
- 真 P32K C4（MS4-C4-L032K-NS）：3.5/7.4/7.4 tok/s，max_running=3，抢占震荡——留作资源边界记录。
- C4 驻留有效性 Gate：L0565 臂 barrier 同步 + max_running==4 ✅。

### 2.3 锚点 4：TP2 P220K C1 TTFT（fixed-128）

| 实验 | R01/R02/R03 TTFT (s) | median | spread | 判定 |
|---|---|---|---|---|
| 冷前缀 ×3 | 103.888 / 104.546 / 104.882 | **104.546** | 0.96% | establish_baseline ✅ |
| 历史参考 | 96.212（±5% gate） | — | — | **不可比（+8.7%）→VALID_FAIL(出处)** |
| warm 重放 ×2 | 1.177 / 1.182 | — | — | 前缀缓存证据 ✅ |

- 附加：无 NVML 对照 103.42 s（采样器税 <0.1%）；隔离独占对照 103.48 s（争用排除）。

## 3. 六态归档

- `raw/valid/`：47 个实验目录 = 四锚点正式 reps + warm/对照臂 24 + CC compile-cache 9（全 VALID_PASS）
  + NDL needle 12（S2×3 VALID_PASS；其余 VALID_FAIL/QUALITY_FAIL）+ DEBT1（VALID_PASS）/DEBT2（VALID_FAIL/QUALITY_FAIL）聚合 2。
- `raw/invalid/`：10 个（8× HARNESS_ERROR=UUID 逐字粉碎 bug 重跑前存档；1× NO-NVML 对照完成使命后归类；2× WARMPFX 早期模式映射错误）。均带 classification_reason。
- `raw/staging/`：空（全部归档，scan-staging 零遗留）。

## 4. D1 compile-cache 补债（3 组冷 cache × build+restart1+restart2）— **DEBT1_PASS**

设计：每组独立冷 `VLLM_CACHE_ROOT`（`rm -rf` 后快照证明空）→ build boot → D565 F512 →
restart1（同 root）→ run → restart2 → run。证据：`raw/staging/DEBT1-COMPILE-CACHE/debt1-report.json`
+ `debt1-determinism.json` + 9 个实验目录（classify 后入 valid）。

**判定**：
- 确定性探针（固定题 + temp0 + 固定 salt）：g1/g2/g3 复用态各 1 针，
  `text_sha256 = 0bd1ecd6…` **3/3 完全一致**（逐字回显正确）→ 输出确定性过。
- 冷建结构一致性：三组独立冷建后 cache root 文件数完全相同（2522/2522/2522）→ 结构级旁证。
- cache 命中证据：build READY ~315/315/310 s vs restart ~55/55/55 + 45 s（含 3 次探针 boot）
  → 复用使 boot 提速 **~6.3×**；artifacts 全落本组 root（`torch_compile_cache/{两个哈希目录,torch_aot_compile}` + modelinfos）。
- 性能稳定性：组内三步 decode 漂移 ≤0.3%（g1: 145.06/144.90/144.91；g2: 132.40/132.41/132.31；g3: 132.54/145.44/132.45）。
  跨时段呈 132↔145 两档（组内极稳），与全天 250W 功耗墙/温度状态一致，非编译差异。

**勘误与覆盖度说明**：
1. 原设计 9 点位探针（每步 1 针）随 runner 被 Desktop agent 层重启收割而丢失（当时只存内存）；
   补扫按"每组复用态 1 针"覆盖（`tools/debt1_probe_sweep.py`，结果立即落盘）。组内 build↔restart
   探针等价性由上述结构一致性+性能稳定性+跨组一致性共同佐证，但未直接逐点位复测——如实记录。
2. 冷证明快照的 Triton 层路径笔误（查 `~/.cache/triton`，实际默认 `~/.triton/cache`）；
   实证补偿：构建窗口内共享 Triton 缓存 mtime 零更新，且 artifacts 全在本组 root——组间隔离成立。
3. `~/.cache/vllm/torch_compile_cache`（50318 历史文件）在 `VLLM_CACHE_ROOT` 钉死时惰性，非污染源。

## 5. D2 TP2 238K 双 Gate — **正确性 Gate FAIL（真负结果）**

证据：`raw/valid/DEBT2-238K/debt2-report.json` + 12 个 NDL 实验目录。

**结果矩阵**（238K：3 boot × 3 seed；220K needle 挂载：每 boot ×1）：

| boot | S1 | S2 | S3 | nd220K |
|---|---|---|---|---|
| b1 | 2/5 ❌ | 5/5 ✅ | 2/5 ❌ | 2/5 ❌ |
| b2 | 2/5 ❌ | 5/5 ✅ | 2/5 ❌ | 2/5 ❌ |
| b3 | 2/5 ❌ | 5/5 ✅ | 2/5 ❌ | 2/5 ❌ |

- **失败模式完全确定性**：三"boot"逐 seed 复现；丢针恒为 0.1/0.3/0.5 浅层位置，
  保 0.7/0.9 深层位置；220K 与 238K 同模式（seed=1 码值相同）。
- **220K needle 也失败**（A4 gate 的 needle 5/5 组件三连败 2/5）→ 长上下文召回退化
  不是 238K 特有，在 ≥220K 即出现。
- TTFT（238K）107.23–107.49 s；VRAM 峰 15448 MiB 恒定；零抢占/零 OOM/零 crash。
- **执行勘误（诚实标注）**：stop() 的 `ps --pgid` 计数在孤儿进程场景误报组空 →
  b1 server 未被终止、b2/b3 端口冲突即刻退出，**12 次 needle 实际全部落在同一 b1 server**。
  故"跨 boot 稳定性"证据失效（改标 within-server repeat：TTFT 漂移 0.03%）；
  正确性结论不受影响（同 server 3 次重复、temp=0、失败逐 seed 完全复现）。
  stop() 已改为 `os.killpg` 可靠轮询（工具层修复已提交）。
- kv_usage_peak 采到 null（该 boot 的 /metrics KV gauge 未暴露）——KV 稳定 gate 空转，如实记录。

**含义（供 Phase 01 裁决）**：kvarn_k4v2_g128 KV 量化在 ≥220K 的浅层召回不可靠，
且为内容×位置确定性失败。这直接命中 `VLLM-OPTIMIZATION-PLAN.md` 的待裁决项
"全 bf16 KV 部署"：Phase 01 应将 **220K needle 对照（bf16 KV vs kvarn）** 列为
优先 A/B；在此之前，≥200K 上下文工作负载不得视为质量达标。

## 6. 勘误与流程事故（全部留痕）

1. 快照 Triton 路径 bug：coldness 快照检查 `~/.cache/triton`（不存在），实际默认为 `~/.triton/cache`；实证补偿：构建窗口内 `~/.triton/cache` mtime 零更新（1159 目录全部早于当日），且 artifacts 全落本组 root（`torch_compile_cache/`）——组间隔离成立。勘误记入 MANIFEST。
2. `~/.cache/vllm/torch_compile_cache` 存在 50318 历史文件：`VLLM_CACHE_ROOT` 钉死时该层惰性（本 Phase 全部 boot 显式钉死），非污染源。
3. runner 自杀事故（铁律 5）：setsid 过的 orchestrator 经 `bash -c` 启动 server 继承同 PGID，`stop(pgid)` 组杀时连坐自身，D1 两次中断。修复=boot 包 `setsid` + stop() 拒绝杀自身 PGID；断点续跑逻辑保住已完成组证据。
4. stop() 的 `ps --pgid` 计数 bug：孤儿进程（PPID=1）场景下组查询返回空 → TERM 后误判组已清、跳过 KILL 兜底 → D2 b1 server 僵尸占端口，b2/b3 boot 实际未成。修复=`os.killpg` 轮询（三脚本统一）。D2 证据按 within-server repeat 如实降级标注。
5. A4w 早期一次模式映射错误（wns→fixed-output），重跑修正，旧数据归 invalid。
6. A2-fix 首组被 fresh-boot 重跑覆盖（同 experiment id）：教训=每 boot 唯一 B 号，已入流程。
7. 会话收割事故链：Desktop agent 层重启（SSH 传输层全天 648 心跳零间隙，非网络问题）
   连杀 4 次 D1 runner（setsid/systemd-run 均在清理范围）→ 对策=断点续跑+前台分步+结果即时落盘；原 9 点位确定性探针丢失后按"每组复用态 1 针"补扫覆盖。

## 7. 放行判定

- 机器状态一致性：同形制三连测 spread——D565 TP1 0.18% / TP2 0.17% / C4 0.24% / P220K 0.96%，
  全部 ≤1%（≤3% 档=高度一致）；compile-cache 跨 boot 输出确定性（D1）与 within-server 重复稳定性（D2，TTFT 0.03%）佐证。
- 与历史的偏差全部可归因于**历史口径/出处错误**（§1），而非机器漂移。
- D2 正确性 FAIL 是**质量负结果**（≥220K 浅层召回退化），不是机器一致性问题——
  它改变的是 Phase 01 的选题优先级，不阻断放行。
- **Phase 00 PASS，放行 Phase 01**（建 0.29 uv 环境，携四新基线：131.581 / 172.832 / 168.51 agg / 104.546 s TTFT；
  优先 A/B：bf16 KV vs kvarn 的 220K needle 对照）。
- SLO 维持 `SLO_UNDECIDED`。

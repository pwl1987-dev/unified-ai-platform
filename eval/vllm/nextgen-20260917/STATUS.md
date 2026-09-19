# STATUS — nextgen-20260917 战役执行状态

> 本文件是执行状态跟踪，不替代仓库 Roadmap/Authority。最终结论回写 docs/VLLM-OPTIMIZATION.md。

- **Phase**: 02（TP2 主基线深挖 → L2/X2 Profile + Gate B，计划 v1.2 机器契约修正版）— **执行中（P0A）**
- **Last Completed**: Phase 01 全相位 P0-P6（2026-09-18，commit `b42fe23`）——**Gate A Overall PASS（A-S ∧ A-X）**；candidate 台账 0.29 复合 profile=PASS / KVarN-on-0.29=REJECTED / FP8=DEFERRED_TO_PHASE03；详见 reports/phase-01-vllm029.md §7
- **Current Task**: P0A 冻结（STATUS reconciliation ✅ → MANIFEST v3 → runtime 终态快照 → schema 1.2 + gates-phase02.yaml 冻结 → 能力探针 → runner 整备）
- **Next Task**: P0B 拓扑双对 Screen → P1 三形制基线 + 9 向分类型 Screen → P2 dynamic-k → P3 Qualify + 双 lineage → P4 L2/X2 + Gate B → P5 收口

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
- 2026-09-18: P2 Layer A TP1 Qualify 收口 + P3 Layer B Screen 收口——LA TP1 3-boot：0.28=57.838 / 0.29=57.863（**+0.043%**，跨 boot 漂移 ≤0.016%，verbatim 双侧 100/100×3）；LB：0.29+DFlash2 首跑（**unit-c 实证必移并移植**：flashinfer 0.6.18 topk JIT 同 CCCL 死，env 开关恢复），F512 0.28=144.962 / 0.29=**146.014（+0.73%）**，**四通路（0.28/0.29×tonly/spec）探针同 hash `0bd1ecd6…` 跨版本逐位无损**，接受率 33.11%→33.43%（+0.33pp）。勘误：boot029 kv-mem=auto 守卫、run_arm --boot-tag、p3 metrics gauge 过滤待宽采。
- 2026-09-18: **P1.2 矩阵收口**——kvarn/bf16 同分布镜像（3 真 boot × S1/S3=2/5、S2=5/5，9/9 格完全确定，Phase 00 跨 boot 债清偿）；seed99 参考码集 6/6 全 5/5；TTFT same-KV reference：kvarn **96.645s**（漂移 0.07%）/ bf16 **104.219s**（0.03%，较 kvarn +7.8%）。P1 全线完成。Layer A TP2 最小资格臂运行中。
- 2026-09-18: Layer A TP2 资格臂 PASS（F512 84.946→84.968 +0.026%、verbatim 100/100、MRV2 实证）——Layer A 双拓扑完整。**Layer B Qualify PASS**：3-boot 中位 0.28=145.008 / 0.29=145.012（+0.003% 逐位级平价），无损探针 8/8 boot 同 hash `0bd1ecd6…`，接受率 33.11%→33.43%（gap +0.33pp << 5pp，地板 20% PASS）。graph-replay gauge 宽采样仍空（`--cudagraph-metrics` 不出 Prometheus 名）——证据路径转 profiler，列 P5 遗留。
- 2026-09-18: **Layer X bridge PASS**——0.29 bf16+spec@220K 生产形制：容量 1.42×、MRV2、seed99/seed2 全中（5/5）、seed1 对照精确复现 2/5（跨版本确定性等价）、TTFT 中位 104.125s vs 同 KV 参照 104.219s（**−0.09%**，门 ≤+5%）。0.29 获得独立于 KVarN 的长上下文资格 profile。
- 2026-09-18: **Layer C 止损（4/6 尝试）**——补丁面浅（11/13 hook 干净、~535 LOC、6/6 导入、KVARN backend 激活、可 boot）但 0.28 flat-tile 内核 × 0.29 V2 带页填充 4D 池的布局契约非重排可解（#2/#4 输出逐字节同损坏、#3 整池拷贝 OOM×2）；正解=内核寻址重写=侵入 core 红线。裁决：0.29 长上下文=Layer X bf16 承接；0.28+kvarn 保留认证；KVarN-on-0.29 入 Phase 03 Debt。清场：GPU2/3/4 18MiB、19701/19702 无监听。
- 2026-09-18: **Gate A-S 机器判定（基于既有证据，2h 门待补）**：性能 0.29 vs 0.28 同形制 = TP1 tonly +0.043% / TP1 spec +0.003% / TP2 tonly +0.026%，全部 ≤3% 高度一致档；质量 verbatim 双侧 100/100×3、四通路无损同 hash、接受率 +0.33pp；MRV2 实证 TP1+TP2。Gate A-X 候选=Layer X（bf16 eligible；needle 全中 + TTFT −0.09%）。终判（A-S AND A-X）待 2h 稳定门与 full-quality 套件（P5 遗留）。
- 2026-09-18: 脱敏勘误——staging 证据 server-log-tail.txt 含 vLLM TP2 启动行 `mq_connect_ip=<本机内网IP>`（2 文件）已按规则表替换为 127.0.0.1；P6 归档批处理须对全部 server-log 类证据自动执行同规则（grep 校验零命中后 add）。
- 2026-09-18: **Phase 02 P0A 收口**——STATUS 顶部漂移勘误（Phase 01 终态=完成/Gate A PASS/b42fe23）；MANIFEST v3（phase02 块）；runtime029_phase02_baseline 终态快照（post-patch tree `4632d624…`/2537 文件、pandas 3.0.6+pyarrow 25.0.1 入册、6 符号 provenance 全 site-packages、integrity CLEAN；**台账 unit-c sha256_after 截断记录勘误**——.orig 差分+mtime 双证为记录缺陷非文件漂移）；schema 1.2 additive（screen_decision/evidence_quality/observation_class + NOT_RUN_UPSTREAM_CAPACITY，双向兼容验证过）；gates-phase02.yaml 全数值化冻结（sha `a9477029…`，metric_sign 对齐 p02_evaluate 提取器实名后重冻）；能力探针（bss 在 V1 unsupported 但 **V2/MRv2 配置级可行**、dynamic-k 对 dflash **源码级不支持**（仅 suffix-decoding）、admission 双旗标 `--max-num-queued-reqs/tokens`、retention `--prefix-cache-retention-interval`、AR 三态实名 VLLM_ALLREDUCE_USE_FLASHINFER/--disable-custom-all-reduce、CG `cudagraph_mode` FULL 枚举）；runner 三件套 p02_common（`_total` 精确名纪律+异族前缀防线，自测 PASS）/p02_screen（config 驱动断点续跑，boot_cmd 干跑 PASS）/p02_evaluate（sign-aware，**冒烟复算 Layer A +0.04% 与 Phase 01 终判一致**）；boot029_nextgen.sh 扩参（9 向旗标 + 配对扫描 --pair-uuids 授权卡防护）。commit `4d4e7ac`。
- 2026-09-18: **现场变化（Phase 02 GPU 工作阻断）**——P0B 启动前巡检发现冻结卡位被外部部署占用：`rpg-bakeoff-*` 容器族（root、docker、生产镜像 0.27.1-cu129）今晚 19:30 起梯度进驻 **GPU2（huihui-opt）/GPU3+4（official-fp8，TP2）/GPU5（humanlike-q4）/GPU6（awq-tgt）/GPU7（uncensored-tgt）**，至 21:25 仍在加速上新；Phase 01 清场终验（GPU2-7 18MiB）在先，非本战役残留。处置：未知进程零触碰（铁律 5），nvidia-smi/docker ps/cgroup/:8000 health 200 全取证留档；P0A 已收口（commit 4d4e7ac）为干净停止点；P0B 起全部 GPU 步骤挂起，等用户裁决（等待 bake-off 退场 / 腾让 GPU3+4 / 暂停）。生产侧 GPU0/1 与 :8000 未受影响。
- 2026-09-18: **P5 收口**——2h 稳定门 PASS（boot gate-a-029c，1370 请求 0 错/canary 24 检 0 败/preempt=0/VRAM 漂移 0.0%）；勘误：preempt_count() 误把 Prometheus `_created` gauge（epoch 秒）计入 → 首判 1.7897e9 假 FAIL，修复后按 `_total` 终值 0.0 重评 PASS（原始+corrected 双 JSON 留痕，流量窗不重跑）。首次尝试 ABORT1（p32k 顶满 max_model_len 142×400）入 invalid/。D565 双曲线：closed C1-C8×3 全 0 败 + Poisson 25-110% 5 点 0 败 P99≤2s（r25 INSUFFICIENT_SAMPLES 44<60 冻结规则）；P220K 容量退化曲线（并发上限 1）。P5-CURVES/P5-STABILITY 按 NDL 最小 manifest 先例归档，staging 清空。
- 2026-09-18: **Phase 01 终判：Gate A-S PASS ∧ A-X PASS → Overall PASS**（reports/phase-01-vllm029.md §7）。candidate 台账：0.29 复合 profile=PASS / KVarN-on-0.29=REJECTED / FP8-KV=DEFERRED_TO_PHASE03。生产切换不自动发生（铁律 9）；0.28+kvarn 认证保留至 Phase 08 窗口。清场终验：GPU2/3/4=18 MiB、19701/19702 无监听、登记 PGID 全退、GPU5-7 未触碰（18 MiB 观察态）、GPU0/1 生产 llama.cpp 未动（pid 5986/6010 驻留）、生产 :8000 只读 health=200。
- 2026-09-19: **P1-TP1CTL 收口（TP1 同栈对照臂，Qualify 3-boot 全成）**——GPU2 空闲窗口先行（GPU3+4 仍被 rpg-bakeoff-fp8 占用）。D565-F512-C1 decode **144.9 tok/s vs Layer B 145.012 = −0.08%**（bf16 显式≡kvauto、MS4 不扰 C1，交叉验证过）；verbatim 3×100/100；P32K 分轨（冷 TTFT 12.6/12.7/13.3s、暖 0.39s、decode 61.9；C2 冷双峰 13-30s=并发第二请求排队 ~2× prefill，NBT2048 分块所致）。B-L2 分母落定：C1 TPOT 6.9ms / C1 冷 TTFT ~12.7s / C2 冷 goodput 0.061rps。D565-C2-F512 3-boot spread 3.79%（>3% 旗标，micro 轴记录在案）。勘误链三条：(1) boot 脚本漏导出 VLLM_DFLASH2_TORCH_TOPK=1（Phase 01 靠 runner 环境携带，新会话丢失→flashinfer topk JIT 死，已固化入配方）；(2) L32 形制 model_len 32768→36864（P32K fixture+输出溢出全 400，gates 勘正 v1 重冻 73ee1366…）；(3) **空-成功陷阱**：bench rc=0 但零请求成功——p02_screen 加 evidence-guard（requests_ok≥1∧http_errors=0∧sum_out≥1 否则 rc=30），旧 12 目录标 SUPERSEDED 留 audit。
- 2026-09-19: **自治续跑链挂起**——`tools/p0b_p1_chain.sh`（taskset 32-63，pid 见 sandbox 锁文件；cron automation-7e8503f6 每小时验活/复活）：等 GPU3+4 腾空（rpg-bakeoff 退场，零触碰）自动执行 P0B 双对扫描（busbw+bench，CPU/NUMA 条件冻结留档）→ B0-L32 Qualify 3-boot → B0-X128/X220 Screen reference；全程断点续跑+每 boot 前重验卡空闲+24h 等待上限。判定/评估留交互会话。
- 2026-09-19: **工作对灵活化（用户拍板）**——不死等 GPU3+4：chain v2（pid 见 sandbox 锁）自动选对，优先级 3+4 > 2+5 > 2+6 > 2+7（GPU0/1 恒禁碰；rpg-bakeoff 零触碰）；任一授权卡腾出即组对开跑 busbw+PAIR-bench+B0 三形制；MANIFEST phase02.pairing_scan.working_pair_flexibility 入册（X2-220K vs Layer X 104.125s 跨对引用 caveat + 3+4 空闲补对照半）。勘误：U6/U7 UUID 凭记忆各有一处 typo，已 nvidia-smi 权威校对。
- 2026-09-19 13:33: **自治链 v2 完整跑完（工作对=冻结 3+4；bakeoff 12:28 退场被抓）**——P0B：busbw 双测 14.34/14.37 GB/s@256MB（|Δ|=0.21%）；PAIR34 前哨 D565-C1 agg 168.58/decode 182.4；对照半与工作半同对复跑（exp 目录覆盖，单测有效，重复证据以 busbw 双测为准）；对照对 2+X 未获得（窗口期 GPU2 被 bakeoff humanlike 占用）→ 按 gates 默认维持 3+4（topo 全 PXB/NUMA0 等价注记）。**B0 三形制全成**：B0-L32 Qualify 3-boot（D565-F512-C1 agg 中位 164.63/decode 177.4/spread 1.40%；C4-NS 201.71 spread 3.20% 旗标；P4K cold/warm 中位 114.89/115.28——COLD cell R02/03 暖污染按分轨解读）；B0-X128（C1 真并发 TTFT 50.6/106.3s、C2 max_running=2 ✓）；B0-X220（C1 bench 暖主导 1.23s，冷 TTFT 由 needle 三态实证 **104.18/104.25/104.30 vs Layer X 104.125 = +0.1%**）。**needle 三态精确复现 Phase 01 签名**：seed1=2/5（命中值逐位同款 941235,900875）、seed99 双档 5/5、seed2@220K 5/5；**新数据点：seed2@128K=2/5**（码集×长度非正交，X128 阳性对照以 seed99 为准）。TP2 vs TP1 预览：C1 decode +22.4%、D565 TTFT −17%、P32K 冷 TTFT −22%。
- 2026-09-19 18:2x: **batch1 终判（14 臂全数据 + B0C24F 同形分母补测）**——screen_decision：**IN = {NBT3072, DRAFT-TP2}**（NBT3072@P32K +17.2%/+17.8% vs 高窗分母为最强信号；DTP2 C1 边际+C4 无伤）；OUT = NBT1024/4096、CG-FULL8/16（FULL 反慢 C1 -3.5%、cap16 C8 -7.7%）、ARFI、ARNOCA（+1.4~2.5% 佳但 <3% 噪声线）、MS1/MS2、MS8（C2 -5.3% 违线，C8 吞吐档 envelope 点留档）、BSS（**boot 级 SUPPORTED 实证——MRv2+spec+bss 共存推翻源码 V1 列表预期**，但 C2 -6.2% 性能回退 OUT）。方法学：B0-L32 三 boot 落全天低点（-2.5% 漂移带），B0C24F（18:1x）与 screen 臂同时段构成受控比较面。勘误：ARNOCA 首轮 extra 误入 boot CLI（rc=2）已修 EXTRA_SERVE_ARGS 通道并补跑 2/2。

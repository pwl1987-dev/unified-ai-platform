# STATUS — nextgen-20260917 战役执行状态

> 本文件是执行状态跟踪，不替代仓库 Roadmap/Authority。最终结论回写 docs/VLLM-OPTIMIZATION.md。

- **Phase**: 03（KV 四路对决 → 三档 Profile + Gate C，v1.1 执行合同）— **执行中（P0A 契约落地完成）**
- **Last Completed**: Phase 02 全相位（2026-09-21）——**Gate B Overall PASS（B-L2 ∧ B-X2）**；composite_L2=B0 配方 / composite_X2=B0+q4 护栏；SLO 定标曲线全档 + ceiling 245K/262K seed99 双 PASS（262,144 模型硬上限；**Erratum EP03-A2：正式 SLO 状态仍 SLO_UNDECIDED**）；详见 reports/phase-02-tp2.md（§11 勘误）
- **Current Task**: P0B L2 终形（P32K spec-off 正式 A/B 先于 KV 主矩阵）
- **Next Task**: P1 KV 四路对决（NATIVE/FP8E4/FP8C/KVARN-0.28 参考）→ P2 三档 Profile → P3 Gate C → P4 收口；TP1-C4 补测=机会式（GPU2 空闲才补）

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

## 2026-09-20 P2-DYNK 终判 ✅（k 阶梯 + TONLY 基线 + k8 复核）
- 链 21:42-22:09 四 boot 全成（K5/K6/TONLY/K8CHECK，同晚窗口互比）。
- **k8 CLOSED**：capture sizes [1,2,4,8] < verify batch 9 → 逐步 graph miss（ms/step 55.1 vs 18.6，decode -65%）；位置8接受非零但双条件不满足。
- **k6 OUT**：全轴被支配（P32K -4.9% vs K7；D565 噪声平手）。
- **k5 IN→Qualify（条件）**：P32K +7.6%（>漂移带）、D565 平手、总接受率 0.446/0.383、KV 容量全 spec 臂最高（+17,362 tok vs K7）；条件=P32K pos1 跨k gap 14.4pp 超地板，Qualify 3-boot 复核，仍超回退 K7。
- **TONLY 结构性发现**：D565 spec 净赢 2.13×（TP2 价值由投机驱动，TP2-TONLY 85.1 < TP1-spec 144.9）；**P32K 全 spec 臂 decode 输 TONLY 21-30%、暖 TTFT 输 33%** —— Phase 03 L2 spec-off 正式 A/B 建议（plan 不加第十方向，如实记录不擅改）。
- 接受率分桶 PARTIAL（聚合计数器无逐请求差分）；drafter/verify 分解 not_exposed（Phase 03 profiler Debt）。
- 证据：raw/staging/P02-SCREEN/p2-dynk-eval.json / p2-dynk-decisions.json / p2-dynk-report.json。

## 2026-09-20 P1-SCR-BATCH2 ✅（policy 三向：match-unit / retention / admission）
- 12+2 boot 链（GPU3+4，RETNONE 预期失败=CLI 拒 int 外值）。fixture 纪律：token 级构造+round-trip/seam 双校验（d565rw/p4krw，rewrite 1/8/32/128×4）。
- **match-unit UNSUPPORTED**：一切显式值（32/64/128）触发 'Disabling fine-grained prefix-cache hits…SlidingWindowManager'（省略旗标无告警），四臂全单元零行为差——混合架构（SW/Mamba 组）强制块对齐，细粒度命中从未生效。在位形态维持。
- **retention OUT**：值域=省略(None=密集)/0(语义)/1024(周期)；显式值 warm_full 全线大退步（0=1.139s、1024=0.318s vs 密集 0.172s，+560%/+85%）；partial 全等；VRAM 0。churn 观察：显式值暖存活 6.2×（0.186 vs 1.155）——Phase 03 稳态画像 A/B 素材。
- **admission：q4 IN**（零排队、503 单调可重试、过载 p95 双钳：p4k 1.85 vs 6.52 / p32k 19.7 vs 24.0；C8 砍半=设计内交换）；q8/q32 OUT（惰性：0 拒绝、waiting≤3）；**x220 在途=1 PASS**（冷 TTFT 103.95 vs 104.125 门 -0.17%，preempt/oom/err 全 0，verbatim 100/100）→ composite_X2 护栏候选。
- 证据：raw/staging/P02-SCREEN/p1-batch2-*（report/cells/openloop/decisions-part1/part2）。

## 2026-09-21 P3-Qualify 终判（12/12 boot 零失败）+ P32K boot 级双峰发现
- **认证轴（spread≤3%）**：C1-D565 无臂过线（NBT3072 −0.6%/K5 −2.3%/DTP2 **−4.4% 认证回退→OUT**）；P4K NBT3072 **+10.7% 真实**、K5 +6.5-6.8%（但 pos1 不过）。
- **P32K 轴 SUSPENDED**：boot 级确定性双峰（58.1 vs 67.6，boot 内 ±0.1%），编译态/容量均不映射；p3_p32k_variance.py 8-boot 表征实验已发射——P4 L2 组装前置依赖。Screen→Qualify 反转 ×2（NBT3072-P32K、DTP2-C1）：单 boot 信号 <2× 门槛一律 provisional（方法论）。
- **K5 pos1 复核不过**（3-boot 复现 +12.7pp > 8pp 地板）→ 按冻结规则回退 K7；规则张力（K5 pos1 高=其总接受率高的机制）如实记录供 Phase 03 复议。
- **Lineage**：composite_L2 = B0 + NBT3072（待 P32K 认证）；portable = NBT3072@X128 recheck（未跑）+ q4 护栏。
- 证据：raw/staging/P03-QUALIFY/{p3-qualify-eval, p3-qualify-decisions, p32k-variance-report}.json。

## 2026-09-21 P32K 方差表征定案 ✅ → 修正协议认证 A/B 运行中
- 8 全冷 boot 实验：**唯一慢 boot = 10h idle 后首个 boot**（57.5 vs 69.9，−17.8%）；随后 7 个 back-to-back boot spread **0.14%**。慢态=平台冷启动惩罚（D565 同向 +5.3%）；与编译态/容量/臂配置无关。
- **认证协议修正**：弃置 idle 后首 boot，back-to-back 入证。生产含义：长上下文冷启动慢态 ~18% → Phase 08 热机手册素材。
- 历史跨窗单 boot 数字（PAIR34/dynk 晚窗等）一律补 ±18% 平台态 caveat；P32K spec-off 结论方向稳健不受影响。
- p3_p32k_certify.py：WARMUP 弃置 + [B0R,N3072]×3 交替（~08:30 完）→ composite_L2 定案 → P4。

## 2026-09-21 P32K 认证 A/B 终判 ✅ → composite 定案
- **NBT3072 @P32K 认证回退 −3.29%**（B0R spread 0.14% / N3072 1.33%，WARMUP 弃置协议）——batch1 +17.2% 信号证伪（慢态分母伪影）。
- **composite_L2 = B0 配方**（forward-addition 集合清空）；composite_X2 = B0 + q4 护栏。P4K +10.7% 短提示轴认证维持→Phase 03 独立候选。
- Gate B 依赖修正协议下 TP2 vs TP1 同窗配对（TP1CTL 属慢态窗，需重测）。
- 证据：raw/staging/P03-QUALIFY/p32k-certify-{report,decisions}.json。

## 2026-09-21 Gate B 机器裁决 ✅ Overall PASS
- **B-L2 PASS**：ttft_p50(C1-P32K) −18.2% ✓ + goodput(C2-P32K) **+596%** ✓（TP1 P32K-C2 预填充串行塌缩 vs TP2 交织）；other-key ttft_p95 −24.2% ✓；tpot(C1) −7% 如实记录（TP1 保单流长上下文 decode，与"聚合吞吐 TP1 对照保留"一致）。TP1-C4 分母挂 GPU2 补测。
- **B-X2 PASS**：seed99 128K 5/5 + 220K 全过；TTFT 220K 103.95（−0.17% vs 104.125 门）；容量边际 1.42/1.78；C4/C8@128K=CAPACITY_LIMIT 端点；designated 口径；q4 在途护栏随附。
- **Overall = PASS**：TP2 适合成为交互/长上下文主基线。
- 证据：raw/staging/P03-QUALIFY/gate-b-verdict.json + GATEB P32K C1/C2 补件（G1/G2 状态锚自洽）。

## 2026-09-21 P4-SLO 双曲线 + ceiling 晋级链 ✅（Phase 02 GPU 实验全部完成）
- **SLO_UNDECIDED 义务解除**：L2（D565 micro + P32K 主曲线）closed C1-C8 + open 5 点全档；X2 P128K closed C1/C2 + C4 CAPACITY_LIMIT 端点（附实测排队补充）+ open 5 点；arrival 列齐全，全点 0 503。
- **ceiling 链全过**：P245K seed99 5/5（TTFT 128.5s，KV 容量 394,941 tok，驻留 1.57×）→ **P262K seed99 5/5（TTFT 133.7s）= 模型绝对硬上限 262,144 工作**；两档均 CEILING_OBSERVATION（正式认证归 Phase 03）。
- 262K 参数化取证：268288>262144 boot 拒绝 → 靶 262000 装配超限 400 → 终靶 261888（离线预验证 262,095≤262,144）——fixture 装配超靶 +153 tok 是根因，靶值偏离透明记录。
- 证据：raw/staging/P04-SLO/{p4-slo-report, p4-slo-decisions}.json + V29-T2-SLO-*/ + SCEIL*/。

## 2026-09-21 Phase 02 终判收口（P5）✅
- **Gate B Overall PASS**：TP2 成为交互/长上下文主基线（composite_L2=B0 / composite_X2=B0+q4）；9 向全部 scalar 胜者死于认证形制（3% 线+多 boot 门槛反向验证有效）；envelope 胜者 q4 护栏 + x220 在途=1。
- 报告 reports/phase-02-tp2.md（§8 六态归档 / §9 Phase 03 Debt 11 项）；DECISIONS.md 新增 9 行正式结论。
- 平台冷启动惩罚（idle 首 boot −18%）+ 认证协议修正三要素 + Screen→Qualify 反转 ×2 制度化（<2× 门槛一律 provisional）。
- 遗留：TP1-C4 补测挂 GPU2（外部 pid 占用，释放即补）；SLO D565 open p95 非单调为 Screen 级小样本（Phase 03 认证重跑）。
- 清场终验：GPU3/4=18 MiB、19701/19702 无监听、登记 PGID 全退、GPU2/5/6/7 外部进程零触碰、GPU0/1 生产未动、:8000 只读 health=200。

## 2026-09-21 Phase 03 P0A 契约落地 ✅（v1.1 执行合同）
- **freeze fail-open 修复（EP03-A1）**：p0a_runtime_freeze.py 重写为 fail-closed 双路契约（uv pip freeze + importlib.metadata，PEP 503 规范化 name→version 比对；rc/空/包数下限/关键包漂移全 FATAL；temp→校验→atomic rename）；重审计 **EVIDENCE_REPAIR 非 ENV_DRIFT**（199 包双路一致，tree sha 4632d624…/patch 18 件/symbol/关键包零漂移）；freeze 文件重写（sha d6ee86e9…，旧 0 字节 e3b0c442… 勘误留档）。证据 repro/env029/runtime029-phase03-inheritance.json。
- **SLO reconciliation（EP03-A2）**：MANIFEST slo_status 维持 SLO_UNDECIDED；Phase 02 报告 §0/§7 追加 Erratum 指针 + §11 正式勘误（曲线≠Authority，不改写历史）；DECISIONS 追加 Erratum 行。
- **gates-phase03.yaml 冻结**（sha 234253…）：KV 四路资格（FP8E4=DIAGNOSTIC_ONLY / FP8C=需 provenance / KVARN=CROSS_RUNTIME_REFERENCE 三禁令）；needle 配对判读（s99/s2/s5 冻结，s99 绝对 5/5 门）；skip_layers 条件触发 bounded≤2；262K 双余量分账 + 四标签（PRODUCTION_SAFE/BOUNDARY_PROFILE/HARD_CEILING_CAPABILITY_PASS/UNSUPPORTED）；238K+ 正式认证门；Gate C 分档判定；暂停条件五条。
- **schema 1.3 additive**（sha 4e9a724f…）：kv_route/route_eligibility/capability_label/cross_runtime_reference/calibration_provenance。
- **能力探针**（repro/capabilities/vllm029-phase03-direction-probes.json）：fp8/fp8_e4m3/fp8_e5m2 CLI 面 SUPPORTED；skip_layers 实名（层索引/类型名）；mamba state 独立 dtype（无 fp8→hybrid 分账实证）；**FP8C 官方通路确认**（k/v_scale 为 checkpoint 参数 + CompressedTensorsKVCacheMethod + parent 模型 kv_cache_scheme=null 槽位在）；**Debt #7 新出口**（--cudagraph-metrics 旗标 + CUDAGraphStat）；Docker 29.1.3+CDI 可用；boot028 冻结配方全量回读。
- **fixture 扩表**：needle-p{238,245,262}k-s{99,2,5}-ph3 9 档 + p245k/p262k prompt；离线 tokenizer 装配验证全过（**新事实：chat 模板 +52 token → 262K 档 position 余量仅 7 token**；238K 余 5467/245K 余 6151）。
- **校准/评测物理隔离**：独立合成语料 64 样本（sha 71b08a93…，seed 20260921，非 ulmus filler 族）+ fixtures/eval/phase03-manifest.json + overlap checker **PASS**（15 needle 码零泄漏）。
- MANIFEST v4（phase03 块）；下一步 P0B（GPU3+4）：P32K spec-off 正式 A/B → NBT3072@P4K → K5 复议 → churn 首跑；TP1-C4 机会式。

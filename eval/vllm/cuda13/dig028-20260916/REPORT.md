# 0.28 深挖第一夜：k 扫描 / dspark+adaptive / ngram_gpu / compile-cache 确定性（2026-09-16 深夜）

> 背景：0.28/cu130 资格认证（本目录上级 `REPORT.md` + `usable-concurrency-20260916/`）完成后，
> 对"还睡着"的 0.28 特性做单变量筛查。GPU2 单卡，配方冻结自 `repro/start028-captured.sh`
> （PYTHONPATH=overlay-kvarn over vllm28-env；kvarn_k4v2_g128 + f16 GDN state + align +
> async scheduling + CG=8 + prefix cache，`--max-model-len 32768` 快速形制）。
> 工具：`tools/boot028.sh`（参数化 boot）、`tools/run_fixture.py`（复用
> `inference/vllm/bench/ulmus_validate.benchmark()`，temp0/seed4242/p565，3 测次 + /metrics 差分）、
> `tools/probe_verbatim.py`（100 条结构化新闻体"逐字复述"探针，复读型负载）。

## 结果总表（32K 快速形制）

| 臂 | decode tok/s | 输出 token | 接受率 | 判定 |
|---|---:|---:|---:|---|
| k=7 dflash2（基线，boot1） | **133.46** | 193 | 29.05%（431/1484） | 现状最优 |
| k=7 复用热缓存第三次 boot（k7c） | **133.47** | 193 | 29.05%（逐位同上） | ✅ 热缓存 boot 确定 |
| k=7 冷编译独立缓存（k7b） | 129.78 | **231** | 28.0%（502/1792） | ⚠️ 冷编译数值分歧 |
| k=6 dflash2 | 130.32 | 190 | 31.7%（415/1308） | 劣于 k=7 |
| k=8 dflash2 | 62.22 | 193 | 26.8%，**pos7 接受=0/206** | ❌ CG=8 掉图 |
| ngram_gpu k=7（通用负载） | 62.09 | **335** | 5.0% | ❌ 无损性嫌疑 |
| ngram_gpu k=7（逐字复述） | 194.8 | 4096(截断) | — | 输给 dflash2 |
| dflash2 k=7（逐字复述） | **224.9** | 5598 | — | +69% vs 通用负载 |

## 四个结论

1. **k=7 是本形制最优点**（CG=8 约束下）。k=6 少 3.1 tok/s（位置 5/6 边际 +0.11 tok/step 盖过
   验证成本）；k=8 灾难性回退：verify 块 9 token 超过 `max_cudagraph_capture_size=8` → 整个
   decode 掉出 CUDA graph 回退 eager（62 tok/s ≈ 无投机水平），且第 8 个候选位置在本 fixture
   上零接受（0/206）。若未来要 k>7：必须同时 CG≥9，且需先证明尾部接受存在。
2. **dspark+adaptive（#51725）不可达**：`enable_adaptive_verification` 仅 method=dspark 合法
   （`config/speculative.py` 显式 raise）；而 dspark 的 draft 权重必须随 target checkpoint 发布
   （或存在 Qwen3DSparkModel 格式 head）——Qwen3.8-27B 没有任何已发布的 DSpark head，
   启用即需新开训练线。负结论，机制清楚。
3. **ngram_gpu 否决**（三重证据）：①无损性违反嫌疑——同一 temp0/seed/prompt 下输出 335 token，
   与 dflash2 各臂稳定的 193 token 不同（投机解码理论上输出必须与 drafter 无关；与 #40880
   家族同味，未做根因）；②通用负载 62.1 tok/s（接受率 5%）；③主场（逐字复述）194.8 反而
   低于 dflash2 的 224.9——**合格的 recal drafter 已吃到重复负载的大头红利**。plain ngram
   另被 async scheduling 直接拒绝（配置校验失败）。
4. **compile-cache 确定性（生产关键）**：同配置三个 boot——冷编译独立缓存（k7b）产生不同
   数值路径（231 token/129.78），复用热缓存（k7c）与 boot1 **逐位一致**（193 token/133.47/
   per-pos {151,107,77,43,29,15,9} 全同）。结论：0.28/kvarn 臂的 boot 间分歧由**冷编译
   autotune 选核差异**驱动；**钉死 VLLM_CACHE_ROOT 后 boot 完全确定**。→ 认证形制必须
   把 compile cache 目录纳入冻结项。09-15 的三 boot 0.033% 极差（native-KV 臂）与本结论
   相容（该三轮共用缓存）。

## 附带量化

- KVarN k4v2 在短上下文的代价：133.5（kvarn）vs 141.6（09-15 native-KV 同 fixture）= **−5.7%**；
  接受率 29.05% vs 32.08%（KV 量化翻转近平局）。这是 245K 容量的入场价。
- 逐字复述负载给 dflash2 带 +69%（133.5→224.9）：模板化/复写型工作流的收益上限已部分兑现。

## 证据

`raw/`：各臂 fixture JSON（含 per-pos 接受分布）+ 复述输出文本。`tools/`：boot 器与探针。
服务器日志未归档（数字均在 JSON；boot 配置见 tools/boot028.sh 与本报告头部配方）。

## 第二夜（2026-09-17 晨）：配置臂 + 前缀探针 + trace 定素

> 用户指示：把 0.28 的点全部逐步挖完。同 fixture 同纪律（每臂独立钉死 compile cache；
> <3% 差异不算赢=冷编译方差实测值）。boot 器已参数化（NBT/MAMBA_MODE/KVARN_POOL_MEM_FRAC/EXTRA_ARGS）。

| 臂 | 结果 | 判定 |
|---|---|---|
| NBT 2048→8192 | decode 正常，**4K prefill 即把 EngineCore 打死**：FLA `chunk_gated_delta_rule_fwd_h` 工作区 `v_new=empty_like(u)` OOM（差 48MiB）——24GB 余量天花板，非逻辑 bug | ❌ 维持 2048；prefill chunk 杠杆是拿 KV 换的，不值 |
| mamba-cache-mode align→all | 133.449 / 193 token / per-pos 与 align **逐位相同** | 零效应，维持 align |
| KVARN_POOL_MEM_FRAC 0.15→0.25 | 133.467 / 逐位相同 | 零效应（C1/32K 下 0.15 池非约束） |
| partial-tail 前缀探针（4K prompt） | 冷 1.667s / 同文重发 0.829s（−50%）/ **尾部改写 0.981s（−41%）** | ✅ #50507 功能验证通过；GDN state 恢复有底价（做不到纯注意力模型的近零），模板化 prompt 工作流受益实在 |
| torch profiler trace（rank0, 11s 窗） | **marlin 83%（6.88s/8.26s，79192 次×87µs）；全 trace 无 248K 宽 GEMM**；kvarn decode stage1/2 ≈107ms；GDN update 12816×12.4µs；sinkhorn 512×210µs | ✅ 定素：drafter=codebook 查表架构，**每步无词表级 matmul** |

**词表截 40K 手术：不适用，证据关闭。** syv-ai 的 +15% 来自其 drafter 每步全词表 lm_head；
我方 DFlash2 selector 是 pred/succ codebook 查表，trace 中不存在对应大核，drafter 整体
成本 ≤6% 步时（1.4GB 权重读取 ≈1.4ms/22.7ms）——手术无肉。

**热缓存 boot 只需 ~50s（冷编译 ~310s）**：运维数据点，配合第一夜"钉死 VLLM_CACHE_ROOT"
配方——生产切换后重启成本极低且逐位确定。

**第二夜不做清单（理由）**：FULL cudagraph+residue 打表（MAX_SEQS=1/k=7 时 verify 批恒为 8，
capture 1..8 已全覆盖，FULL 只在批形状变化时有意义=多并发场景）；CG=16/k=8（pos-7 接受
0/206，结构性零上行）；0.29 升级（overlay-kvarn 补丁面向 0.28 文件，跨版本重打补丁是独立
工程，Fast Math/ZMQ 增量对本单流场景预期 <3%）；suffix decoding（需 arctic-inference，
ngram 同类，ngram_gpu 已三重否决）；P-EAGLE/FastMTP（需自训 head）。

**两夜总结论**：认证配方（k=7/NBT2048/align/0.15/CG8/f16 state/kvarn k4v2）**就是当前
证据下 24GB 单卡 32K 形制的局部最优**；所有廉价杠杆已穷尽，剩余上行只存在于
①生产切换本身（0.28 vs 0.27.1 生产镜像）②多并发场景重测（C4+，cudagraph/池参数可能在
那里有戏）③新 drafter 架构（EAGLE-3.1 类，需训练线）。

## 第三夜（2026-09-17 晨）：并行 GPU 战役 —— 并发/CG/多卡 TP2（commit 530f6ad）

> 用户指示：闲置 GPU 并行测试 + 性能测试 + 多卡测试。三臂并行（P1=GPU2 CG16/MS4、
> P2=GPU7 CG8/MS4、P3=GPU3+4 TP2/MS4，各独立 cache 并行 boot），bench_conc.py 并发 fixture
> + 标准 fixture 交叉校准。注意 bench_conc 的 aggregate/per-stream 含 TTFT，纯 decode 以
> run_fixture 口径为准。

| 臂 | C1 纯 decode | C4 aggregate（含TTFT） | 判定 |
|---|---:|---:|---|
| 单卡 MS4（CG16 / CG8 双胞胎） | 127.31 / **126.95**（逐位级一致） | 200.0 / 197.5 | CG 在 C4 也无差；**MS4 本身对单流收 ~5% 税**（vs MS1 的 133.5） |
| **TP2（GPU3+4）** | **177.26（+32.8% vs 单卡最优 133.5）**，接受率 32.96% | 149.6 | **单流大胜**；C4 aggregate 反而低于单卡（allreduce×并发税） |
| TP2 @245760（220K prompt C1） | **TTFT 96.2s（vs 单卡 0.28 的 186.2s = 1.93×）**；decode 39.5 tok/s@220K | — | 预填近线性加速；KV 池翻倍余量；长 ctx decode 的单卡同点对照缺测（遗留） |

**机理**：batch=1 decode 是带宽瓶颈，TP2 每卡只读一半权重（~9GB/步），PCIe allreduce
每步仅 ~2.6MB——读带宽近 2× 并行；接受率还回升到 32.96%（≈native KV 水平，TP 数值路径
差异，未深究）。C4 时 verify 计算量上去后 allreduce 税变重，TP2 aggregate 反而落后单卡。

**结论**：TP2 是单流延迟敏感场景（编码助手/终审通道）的**最优拓扑**（+33% decode、TTFT
近 2×、KV 翻倍）；单卡仍是并发聚合场景最优。这直接改写生产拓扑选项：8 卡可容纳
2×TP2 对 + llama.cpp 双副本。遗留：TP2 长上下文 decode 的单卡对照；TP2+245K 的多 needle
精度门；C8/C2 中间点。

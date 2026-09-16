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

## 遗留（未测，按价值序）

FULL cudagraph + residue 打表（syv-ai 法，CG=8→FULL）；draft 词表截 40K（须语义门）；
0.29（Fast Math Mode/ZMQ IPC）；k8+CG16（仅在有证据尾部接受>0 时值得）。

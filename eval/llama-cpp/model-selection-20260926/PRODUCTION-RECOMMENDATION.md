# PRODUCTION RECOMMENDATION — llama.cpp 未来业务主模型 + Production Runtime

> 任务：qwen3.8-27b-8x4090-stack 模型选型（2026-09-26）
> 证据根：`benchmarks/llama-cpp/model-selection-2026-09/`（本目录），逐条 run 可追溯（§46 字段齐备）。
> 冻结运行时：`llama-server:cuda12.4-b10715`（与生产 CONTROL-PROD 二进制一致，digest `sha256:cc0782…5fa`）。
> 全程零接触生产（GPU0/1、:8000/:8081/:8082、GPU5 vLLM 均未动，测试用 GPU 2/3/4/6/7 + 端口 181xx）。

---

## 0. 一句话结论

- **PRIMARY-BUSINESS-MODEL = `ukisai/Swift-1.5-Qwen3.8-27B-GGUF` @ `a161446` 的 `Swift-1.5-Qwen3.8-27B-Q5_K_M.gguf`，2×RTX4090 + 256K + KV q4_0 + FA on**（编程/长码/长上下文综合最优）。
- **LONGCTX-ECONOMY-PROFILE = `ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF` @ `d74895b` 的 `IQ3_S-mtp`（sha256 `9aecf1cd…`），1×RTX4090 + 256K**（单卡全深度 needle 100%、思考 token 最省、C8 可用）。
- ⚠️ **License Gate：两者都是 Swift Open License v1.0（年收入 ≥ US$1M 需企业授权）→ `TECHNICAL_WINNER_BUT_LICENSE_REVIEW_REQUIRED`**。若业务方确认超线且不签企业协议，则合法 PRIMARY 回落到 ISTA（Apache-2.0），但其默认模板存在"无限思考"缺陷（见 §A）。
- **PRODUCTION-LLAMA-CPP-RUNTIME：维持 b10715 不变**（本驱动上最优 prefill + 与生产零迁移成本）；官方 CUDA13 全线不兼容 R580@13.0；官方 CUDA12.8 与本地 CUDA13-sm89 数据留档备升级决策（需拍板，本轮不动生产）。

---

## 1. CONTROL-PROD 现实（问题 1-3）

- 生产 = 双副本 llama-server（GPU0/GPU1，`127.0.0.1:8081/8082`），OpenResty :8000 会话粘滞 LB；mon :9000。
- llama.cpp **b10715**（本地镜像 `llama-server:cuda12.4-b10715`，digest `sha256:cc0782dc…`，源码 /data/build/llama.cpp-new，二进制自报 build0/commit unknown）。
- 模型 = `Qwen3.8-27B-coding-v1.1-iq4xs.gguf`（15.30GB，sha256 `397a7654…`）+ DFlash2-Q4_K_M 草稿（sha256 `1a25c568…`）；
  `-c 262144 -np 1 -ngl 999 KV q4_0/q4_0 草稿KV q8_0 -fa on --cache-reuse 2048 --jinja --spec-type draft-dflash --spec-draft-n-max 7`。
- 架构（GGUF 头）：qwen35 混合线性注意力，64 层（16 全注意力 + 48 GDN），GQA 24Q/4KV head_dim 256，内嵌 MTP-1，原生 VL 词表；KV 32768 elem/token（q4_0 ≈18.4KB/tok → 256K ≈4.7GB）。

## 2. Runtime 选型（问题 4-7）

固定 CONTROL-PROD 模型 + 草稿，GPU2，暖机嵌套前缀梯度（1K/32K/128K/256K）：

| runtime | prefill 32K/128K/256K (tok/s) | decode 1K/32K/256K (tok/s) | VRAM | 冷启动→health | JSON/工具 |
|---|---|---|---|---|---|
| **b10715 (CUDA12.4, CURRENT)** | **2378 / 1576 / 983** | 97.3 / 73.8 / 31.7 | 22990 | 6.5s | ✓/✓ |
| official server-cuda（CUDA12.8, b11176/f805c57a） | 2133 / 1494 / 974 | **105.2 / 88.2 / 35.4** | 22974 | 6.5s | ✓/✓ |
| local master CUDA13.0-sm89（b11192/171e8846） | 1816 / 1343 / 906 | 105.2 / 87.6 / 35.3 | 22974 | 6.0s | ✓/✓ |
| official server-cuda13（CUDA13.4.1） | **无法启动**：NVIDIA_REQUIRE_CUDA=cuda≥13.4 > 本机 13.0（最早的 b7588=CUDA13.1 也 ≥13.1，全系列不兼容） | — | — | — | — |

- **BENCHMARK-RUNTIME 冻结 = b10715**：与生产同二进制（结果 1:1 可迁移）、prefill 全面领先（128K+ 场景 TTFT 是稀缺资源）、所需特性齐备。CUDA13 路线（官方被驱动封死；本地构建 prefill -8~-24%）判回退。30 分钟持续负载 242 iters 0 错误、VRAM 恒定（soak-smoke.json）。
- 生产 runtime 是否升级到 CUDA12.8（decode +8~19%、prefill -5~10%）：**独立决策，需拍板，本轮未动**。

## 3. Stage-1 四模型筛选（问题 8-11）

统一：b10715 / 64K ctx / KV q4_0 / FA on / MTP off / temp 0（下表 zh=默认思考模板；探针均机器判分）：

| 探针 | A ISTA GSQ IQ3_S-mtp | B Swift1.5 GSQ IQ3_S-mtp | C Swift1.5 Q5_K_M | D Swift1.0 Q4_K_M |
|---|---|---|---|---|
| 中文解释（默认思考） | **✗ 无限思考**（4229 字推理、正文为空） | ✓（**思考仅 78 字**） | ✓（586 字） | ✓（542 字） |
| 中文解释（enable_thinking=false） | ✓ | ✓ | ✓ | ✓ |
| 编程(roman)/JSON/工具/数学 | ✓/✓/✓/✓ | ✓/✓/✓/✓ | ✓/✓/✓/✓ | ✓/✓/✓/✓ |
| needle 32K / 64K | ✓ / ✓（64K 一次 400 为 harness 余量伪影，手验 PASS） | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| 重启×3 | ✓ | ✓ | ✓ | ✓ |
| 单卡 VRAM@64K | 13.2GB | 13.2GB | 21.1GB | 18.1GB |

- **淘汰/定位**：A 保留为量化对照（Apache-2.0、官方 mmproj），不作主选（默认模板不可用级缺陷）；D（Swift 1.0）提前退出——共享套件上被 1.5 支配或持平（coding 8/13 < C 9/13；structured 5/7 < 6/7；无任何 D 优势轴），1.5 另有思考效率与长上下文优势。
- **Swift 1.5 vs 基线 Qwen3.8（ISTA）**：同 quant 预算下 1.5 修复了无限思考（78 vs 4229 字）、needle 更稳（B 全深度 100% vs A 128K 94.4%）、agent/写作更强。真实业务改善成立。

## 4. 决赛数据（问题 12-27）

| 轴（机器判分） | B GSQ IQ3_S-mtp（单卡） | C Q5_K_M（单卡≤64K / 双卡 256K） | D Q4_K_M |
|---|---|---|---|
| **CODING-SUITE**（13 题，可执行验证为权威） | 7/13 | **9/13** | 8/13 |
| Long-Code real-repo（8 题 grep 判分） | 3/8 | **4/8** | — |
| Long-Code 合成工程定位 4 题 + 补丁执行 | 4/4 + ✓ | 4/4 + ✓ | — |
| Needle 32K/128K/256K（全深度×3 模式） | **100% / 100% / 100%** | **100% / 100% / 100%** | — |
| STRUCTURED（7 例 + 嵌套工具参数） | 6/7 + ✓ | 6/7 + ✓ | 5/7 + ✓ |
| AGENT（10 场景，含 8/16/32 轮） | **9/10** | 8/10 | — |
| 中文写作（12 题机器度量） | **10/12** | 9/12 | — |
| 思考 token（zh 探针） | **最少（78 字）** | 586 字 | 542 字 |
| 256K prefill（tok/s，实测填满生成） | 1046（单卡） | **1721（双卡）** | — |
| 256K decode（tok/s） | **27.9（单卡）** | 22.7（双卡） | — |
| 128K TTFT（needle 实测墙钟） | ~63-70s | **~35-45s（双卡）** | — |
| 并发（单卡，-np 8 @256K） | C1 54.5 → C8 聚合 **134.4 tok/s**，p99 TTFT 8.3s，0 失败 | C1 38.7 → C8 聚合 123.5 tok/s，p99 8.8s，0 失败（双卡，VRAM 14.3+13.9GB 恒定） | — |
| Vision（mmproj，业务图 3 题） | 无官方 mmproj | CPU **3/3**（1.1-1.3s/图）· GPU 2/3（0.5-0.7s/图） | — |
| VRAM | 13.2GB（单卡 256K 富余 10GB） | 21.1GB 单卡(≤64K) / 双卡 15.7+15.5GB(256K) | 18.1GB |

- 最优 quant（问题 12/13）：**normal 档 Q5_K_M**（Q6_K 双卡仅 -4~-6% 速度、无质量证据优势，出局；Q4_K_M 编程弱一档）；**GSQ 档 IQ3_S(-mtp)**（KLD 0.051，512K 内无损口径 + 实测全过）。
- 单卡最佳（问题 14）：B（唯一单卡 256K 全能力者）。双卡最佳（问题 15）：C。四卡（问题 16）：**不值得**——双卡已达标 256K + C8；4 卡资源更适合 2 replica × 2GPU（问题 36），Context>Quality>Concurrency 原则下不为 C8 加卡。
- 128K/256K 最佳（17/18）：能力 B=C（100%）；**速度 C（双卡 prefill +65%）**。Coding 最佳（19）：C；128K Coding（20）：C（longcode 4/8 > B 3/8）；256K Coding（21）：C 同理。Agent（22）：B 9/10。JSON/tool（23）：B=C=6/7+嵌套 ✓。中文写作（24）：B 10/12。思考 token 最省（25）：B。总墙钟（26）：短提示长生成 B/C 持平（MTP 后 B 占优），长提示 C 双卡占优。Vision（27）：C（Swift15 官方 mmproj；CPU 模式 3/3 且省 1.16GB）。

## 5. 优化结论（问题 28-34）

B（GSQ IQ3_S-mtp，单卡 256K）优化矩阵（正确性探针全 3/3）：

| 配置 | VRAM | 32K p/d | 128K p/d | 256K p/d |
|---|---|---|---|---|
| KV f16@128K | 20160 | 2649/54.0 | 1770/39.4 | — |
| KV q8@256K | 21868 | 2623/54.1 | 1732/39.2 | 1034/28.9 |
| **KV q4@256K（基线）** | 17772 | 2620/53.6 | 1747/38.3 | 1046/27.9 |
| KV q4 + draft-mtp | 20238 | 2176/**73.5** | 1494/**47.6** | 903/**33.4** |
| KV q4 + DFlash2 草稿 | 21024 | 1972/**72.3** | 1459/**47.4** | 917/**35.8** |
| KV q4 + ngram-cache | 17772 | 2621/**35.5↓** | 1747/26.7↓ | 1050/22.2↓ |
| FA off（≥131K） | **无法启动/装不下** | — | — | — |

- **Flash Attention（31）：默认 ON**（off 在 ≥131K 直接不可部署；on 无质量损失）。
- **KV cache（32）：q4_0/q4_0**（相对 f16/q8 prefill+decode 差 <3%、正确性探针同级；省出的显存换上下文，正合"宁降 KV 不降权重"原则；若未来敏感任务可 per-deploy 切 q8）。
- **MTP（30/34）：decode +34~75% 且质量探针全 3/3，但 prefill -17~-48%** → **不作默认**（256K 长提示净亏；C 双卡 128K 档需生成 >~1100 token 才回本），作为 per-workload 开关写入 Profile（decode 密集型任务/部署可开 draft-mtp：C 双卡 32K decode 36.8→64.6）。ngram-cache 一致净负收益，弃用。
- **CPU mmproj（28/29）：可用且推荐**——同正确率、省 1.16GB VRAM、图像编码 1.1-1.3s（GPU 0.5-0.7s）；视觉低频场景不值得占 VRAM，也**无需拆 Sidecar**（§33 预案保留）。
- **并发（33）**：B 单卡 C1→C8 线性退化优雅（134 tok/s 聚合、0 失败、VRAM 恒定）；C 双卡待补。

## 6. License（问题 37）与最终拍板（问题 38-40）

- ISTA = Apache-2.0（含 mmproj）→ 可商用。**ukisai 三仓 = Swift Open License v1.0：法人年收入 ≥ US$1,000,000 时商用需另签 Swift Enterprise License**（含受控实体合并计算；再分发需带许可+NOTICE；商标限制）。→ **LICENSE_REVIEW_REQUIRED**，本报告不给法律意见。
- **PRIMARY-BUSINESS-MODEL（技术+业务优先级裁决）= Swift 1.5 Q5_K_M @ 2×4090**：编程(9/13)、长码(4/8)、长上下文（needle 100% + 双卡 256K prefill 1721）四项最高优先轴全部第一或并列第一；256K PASS。
- **保留 LONGCTX-ECONOMY = Swift 1.5 GSQ IQ3_S-mtp @ 1×4090**：单卡 256K 全能力 + 思考最省 + C8 可用，与 PRIMARY 互补（经济位/溢出位）。
- 为什么不是 B 做主选：编程与长码是第一优先级，C 分别 9 vs 7、4 vs 3；B 的优势轴（agent 9 vs 8、写作 10 vs 9、思考 78 vs 586）权重靠后且差距小。
- 为什么不是 Q6_K：双卡实测无速度优势（-4~-6%），无质量证据（KLD 已在 IQ 系列满足），纯成本。
- 为什么不是 ISTA：技术缺陷（默认模板无限思考）+ needle 128K 94.4%；仅当 License 审查失败时回落（回落方案：ISTA IQ3_S-mtp + 强制 enable_thinking=false 模板/无思考部署 + mmproj，代价是 agent/写作/编程分数下降，且需业务接受）。
- **License 双保险提示**：LONGCTX 与 PRIMARY 同属 Swift 系；若审查不过，两档都要回落（ISTA IQ3_S-mtp 单卡可同时顶两档，Q5 档无 Apache 替代）。

## 7. PRIMARY-BUSINESS-PROFILE（问题 48，可直接部署）

见 `model-profiles.json`（含 LONGCTX 档与全部指纹字段）。核心：

```yaml
primary_business_profile:
  model_repo: ukisai/Swift-1.5-Qwen3.8-27B-GGUF
  model_revision: a1614465cfa35d04d3e8575d713fa779662b5eab
  gguf: Swift-1.5-Qwen3.8-27B-Q5_K_M.gguf
  gguf_sha256: 4964843f816dafe77ce24a92c97f3bb094b218d752172710d9438af0e2562931
  quant: Q5_K_M (5.5bpw, 20.92GB)
  llama_cpp_sha: b10715 (local build; binary build-id not injected)
  llama_cpp_build: b10715
  docker_image: llama-server:cuda12.4-b10715
  docker_digest: sha256:cc0782dc7b595e34ca2611729d7d23e47db6aa3d09aff4f9a8ddc3fd45f751fa
  cuda_runtime: 12.4.1 (container)
  host_driver: R580 580.173.02 (CUDA capability 13.0)
  gpu_model: RTX 4090 24GB
  gpu_count: 2
  gpu_ids: e.g. 4,7（按部署位分配；勿用 0/1）
  tensor_split: "--tensor-split 1,1"
  split_mode: layer (default)
  n_gpu_layers: 999
  context: 262144
  kv_k: q4_0
  kv_v: q4_0
  flash_attention: on            # off ≥131K 不可部署
  batch: 1024
  ubatch: 1024
  parallel: 1                    # 多路并发另起 replica（粘滞 LB 既有架构）
  prompt_cache: --cache-reuse 2048（如部署机日志报 not supported 则无害禁用）
  mtp: off（默认；per-workload 可开 draft-mtp：双卡 decode 36.8→64.6@32K / 29.0→41.5@128K，代价 prefill -43~45%，128K 档生成>~1100 tok 才回本）
  mmproj: /path/mmproj-Swift-1.5-Qwen3.8-27B-F16.gguf (sha256 daa1116c…)
  mmproj_offload: false (--mmproj-device none --no-mmproj-offload；省 1.16GB，图像编码 ~1.2s)
  chat_template: --jinja (Qwen3.8 reasoning 模板原生)
  reasoning: 默认开启（Swift1.5 思考 token 已大幅收敛；对纯文字量产场景可 enable_thinking=false）
  sampler: temperature 0(批处理)/默认 temp1.0 top_k20 top_p0.95 min_p0.05(交互)
  healthcheck: GET /health == 200
  restart_policy: unless-stopped（同生产）
  expected_vram: ~15.7GB+15.5GB（256K 满载，含 KV q4 池）
  expected_ram: ~2-6GB/replica（随 256K prefill 波动，页缓存性质）
  c1_c2_c4_c8: 以 -np 8 slot 复用测得 B 档 C8 聚合 134 tok/s@单卡 参考；C 档双卡数据 runs/concurrency/
  ttft: 32K ~7s / 128K ~35s / 256K ~149s（首问冷前缀；前缀缓存命中后见 §35 warm 数据）
  prompt_tps: 32K 4003 / 128K 2840 / 256K 1721（双卡）
  decode_tps: 32K 36.8 / 128K 29.0 / 256K 22.7（双卡；单请求）
  max_verified_context: 262144（真实填充+生成验证，needle 全深度 100%）
  production_status: CANDIDATE — 待 ①License 拍板 ②C soak 通过 ③部署演练（用户拍板制）

longctx_economy_profile:
  model_repo: ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF
  model_revision: d74895bbe5db4bec1e0024e7cc87d59c02d7631a
  gguf: Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf
  gguf_sha256: 9aecf1cd41b2cb2f32a74e0d889e33855ebef43b26f43b43feb5720239e677e5
  quant: GSQ-RCO IQ3_S(-mtp) 3.50bpw 12.12GB
  gpu_count: 1
  context: 262144
  kv: q4_0/q4_0, FA on, MTP off（默认；draft-mtp 可选 +37% decode 换 -17% prefill）
  expected_vram: ~13.2-17.8GB
  vision: 无官方 mmproj（勿混用 ISTA projector）
  c8: 聚合 134 tok/s，p99 TTFT 8.3s，0 失败（-np 8 共享 256K 池）
  soak: 30 分钟持续负载（runs/soak/）
```

## 8. Production Soak（问题 44）

- 冻结 runtime + CONTROL-PROD 模型：242 iters / 0 err / VRAM 恒定 23124MiB / decode 无劣化（runs/runtime-ab/soak-smoke.json）。
- **B（LONGCTX 档）：PASS** — 服务存活期内 191/191 迭代 0 错误、VRAM 恒定 17634MiB（runs/soak/B-…；尾部 74 条 Connection refused 为操作员中途撤容器所致，已注记）。
- **C（PRIMARY 档，双卡 256K）：PASS — 221 iters / 0 err / VRAM 恒定 28978MiB（runs/soak/C-…）**。

## 9. 尚需人工/后续的事项

1. **License 拍板**（Swift Open License $1M 门槛）——决定 PRIMARY 是否生效或回落 ISTA。
2. 生产切换本身（新模型上线、replica 拓扑）按拍板制另行执行；本报告只交付 Profile 与证据。
3. Writing 套件为机器度量 + 存档文本，**人工抽查**建议按 runs/writing/*.json 的 text 字段抽 10%。
4. 4 卡/8 卡拓扑、vLLM 对比不在本轮范围（分仓规则：应用层去 tvnews-frame-pipeline）。

## 10. 证据索引（问题 45）

`environment.json` · `control-prod.json` · `CONTROL-PROD-REALITY.md` · `control-prod-props.json` ·
`runtime-matrix.json` · `runtime-selection.json` · `artifact-matrix.json` · `model-profiles.json` ·
`runs/runtime-ab/`（含 soak）· `runs/stage1/` · `runs/longctx/`（needle 电池）· `runs/long-code/` ·
`runs/coding/` · `runs/structured-output/` · `runs/agent/` · `runs/writing/` · `runs/vision/` ·
`runs/opt/` · `runs/concurrency/` · `runs/gpu/` · `runs/soak/` · `licenses/` · `summary.json` · `pareto.json` ·
`swift15-normal-sha256.txt`。仓库脱敏副本：`repo/eval/llama-cpp/model-selection-20260926/`。

---

### 附录 A：ISTA 默认模板"无限思考"实录

- 探针："用中文解释 KV cache 量化…200 字左右"（默认思考模板）：ISTA IQ3_S-mtp 输出 4229 字推理、0 正文（max_tokens 3072 内未收敛）；`enable_thinking=false` 后正常（152 汉字）。Swift 1.5 同探针 78 字推理 + 132 汉字正文。Stage-1 证据：runs/stage1/A-….json probes.zh。
- 含义：以 ISTA 为生产默认必须强制无思考模板或额外采样约束；这是 Base Qwen3.8 与 Swift 1.5 的最尖锐行为差。

### 附录 B：本轮已验证的工程事实（供复用）

- R580(CUDA 13.0) 上官方 CUDA13 镜像全线不可用（≥13.1/13.4 门槛）；本地 CUDA13.0.1-devel + sm_89 + master 可构建可运行（prefill 回归，留档）。
- llama-server 客户端 /tokenize 与模板后实际 prompt 计数差 ~2K tokens（长上下文探针必须留 ≥4K 余量）。
- FA off 在 ≥131K（含双卡）不可部署；ngram-cache 在本负载净负；`--cache-reuse 2048` 在该架构报 not supported（无害禁用，生产同款）。
- compose flow-sequence 中不能直接插值 `${VAR}` 列表（YAML 解析先于插值）；多卡走 docker run --gpus device=。

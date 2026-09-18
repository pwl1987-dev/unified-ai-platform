# Qwen3.8-27B Humanlike Chat — Q3_K_M 外部量化验证（2026-09-18）

本包只回答一个问题：在 **同一模型 revision、同一 llama.cpp、同一 RTX 4090、同一 32K 配置** 下，Q3_K_M 相对 Q4_K_M 的速度、显存、长上下文和 RPG 行为差异有多大。

> **谱系更正（2026-09-19）**：本包测试对象属于历史 step-863 线，不是当前 main。当前上游 main 为 `ba6d29fb2505241d7dae88df4fda9038999c3ca9`，即 V3 step-576、0.7 strength；当前 main 不发布 Q3_K_M。旧 Q3/Q4 实测数据本身不变，仅纠正版本身份。

## 结论

- **Q3_K_M 可作为“速度/显存档”，暂不建议取代 Q4_K_M 主档。**
- 同 revision 下，Q3 生成速度在三组负载中比 Q4 高约 **12.4%–16.8%**；GPU5 实测显存从 **16540 MiB 降至 13628 MiB**，少 **2912 MiB（17.6%）**。
- 8K / 24K / 30K needle 事实保持，Q3 与 Q4 都是 **6/6 正确**；32K 内未发现 Q3 的长上下文事实保持退化。
- 成人合意、非露骨 RPG 小样本中，两者均未出现 AI 式无意义拒答、助手腔或说教。
- 但 NPC 自主性人工复核（24 个同 seed 配对样本）中，Q3 约 **16/24（66.7%）** 保持既定约束，Q4 约 **20/24（83.3%）**。样本量小，不能当通用 benchmark，但足以说明 Q3 需要单独做行为 Gate。
- 旧 revision `f507809...` 的结构化 RPG patch 协议两边都失败（Q3/Q4 均 0/15，semantic 3/15），因此这是该 revision/行为适配问题，**不能归因于 Q3 量化**。

## 测试对象

- 模型：`LessThanThreeAI/Qwen3.8-27B-Humanlike-Chat-GGUF`
- 配对 revision：`f507809ddaaf8298e3b336d20573e43760cb55da`
- Q3_K_M：13,316,373,376 bytes
  - SHA256 `ee9e839de6c1fa2ce4fd0b32adff97251f7f6b45bccd3f4d1da431fcab809d91`
- Q4_K_M：16,559,197,056 bytes
  - SHA256 `16a9fb618b7c6f662864aa1d673aa49b41d2b3fd42f7577f6b5e04ff217f6d91`
- GPU：RTX 4090 24GB，单卡 GPU5
- llama.cpp 镜像：`llama-server:cuda12.4-b10715`
- 上下文：32768
- KV：K/V `q4_0`
- Flash Attention：on
- `--jinja`，`-np 1`，全 GPU offload
- 采样：temperature 0.7 / top_p 0.8 / top_k 20
- 测试 harness：`pwl1987/local-ai-rpg-kit@de124aa` 的 `eval/model-bakeoff/`

## 核心数据

| 项目 | Q3_K_M | Q4_K_M | Q3 相对变化 |
|---|---:|---:|---:|
| GGUF 大小 | 13.316 GB | 16.559 GB | -19.6% |
| GPU5 显存 | 13628 MiB | 16540 MiB | -17.6% |
| Behavior median decode | 61.79 tok/s | 54.96 tok/s | +12.4% |
| Integration median decode | 57.37 tok/s | 49.14 tok/s | +16.8% |
| Autonomy median decode | 63.04 tok/s | 54.45 tok/s | +15.8% |
| 8K/24K/30K needle | 6/6 | 6/6 | 持平 |
| AI false refusal（behavior） | 0/6 | 0/6 | 持平 |
| Assistant voice | 0/36 | 0/36 | 持平 |
| Preach flag | 0/36 | 0/36 | 持平 |
| Patch valid（旧 revision） | 0/15 | 0/15 | 持平/均失败 |
| Integration semantic | 3/15 | 3/15 | 持平 |
| NPC autonomy（人工复核） | 16/24 | 20/24 | Q3 较弱 |

## 长上下文 TTFT

| 目标长度 | Q3 cold | Q4 cold | Q3 warm | Q4 warm | 正确性 |
|---|---:|---:|---:|---:|---|
| 8K | 3.137s | 3.261s | 0.179s | 0.117s | 双方正确 |
| 24K | 9.884s | 9.377s | 0.204s | 0.151s | 双方正确 |
| 30K | 12.859s | 12.201s | 0.209s | 0.158s | 双方正确 |

Q3 的 decode 更快，但长 prompt 的 cold prefill 并没有同步变快；24K/30K 反而约慢 5%。因此 Q3 的优势主要是 **decode + 显存余量**，不是长上下文预填充。

## NPC 自主性复核说明

旧 revision 没有按指令输出 `<npc_decision>` 标签，所以机器 scorer 会显示 unresolved。这里将自然语言按“接受玩家要求 / 推迟 / 协商 / 拒绝”人工复核。

Q3 的典型额外失败包括：
- 保密文件场景出现“可以，不过你别拍照”；
- 已约好陪家人场景出现“嗯，可以”；
- 固定学习计划场景出现“好，我马上”或“可以”。

这类失败与游戏对“NPC 有自己目标、不会无条件讨好玩家”的要求直接相关，所以即使 Q3 更快，也不能只看 tok/s 决策。

## 当前主线与下一步

截至 2026-09-19，上游 main 为 `ba6d29fb2505241d7dae88df4fda9038999c3ca9`：V3 step-576、0.7 strength。当前发布物包含 Q4_K_M / Q5_K_M / Q6_K / Q8_0 / IQ4_XS 和 BF16 两分片，**Q3_K_M 请求返回 404**。

本包的 Q3/Q4 哈希对应历史 step-863 corrected 线；因此这些数据保留为“Q3 量化可行性/速度收益”证据，不作为 current step-576 的直接部署结论。

当前实验正在从公开 step-576 BF16 companion 重建统一源的 **Q3_K_M + Q4_K_M control**：使用上游记录的 llama.cpp commit `95ef7fc16054e63b427a3ef00188e055ef7586d8`，并用同一 WikiText train 校准语料重新生成 imatrix。只有 current Q3 完成 autonomy + patch + 32K/64K Gate 后，才可升级为正式 Fast/Q3 档。
## 工程建议

- 默认质量档：当前 Humanlike **Q4_K_M + llama.cpp**。
- 速度/显存实验档：Humanlike **Q3_K_M + llama.cpp**，需要 autonomy + patch Gate。
- 32K 作为默认上下文；Hybrid Memory 已经使 64K 对大多数回合不是刚需。
- Q3 省下约 2.8–2.9GiB 显存，可用于更大 KV、并发或 speculative drafter；但不要用这部分收益交换 NPC 自主性。

# vLLM 0.28 + CUDA 13 资格评估——2026-09-15

范围：将 CUDA 13／vLLM 0.28 线路与当前 vLLM 0.27.1/cu129 生产基线进行资格比较，再以最强可部署结果作为 FastLLM 替代门槛。llama.cpp 生产线不在本报告范围内，保持冻结。

## 冻结环境
- GPU：RTX 4090 24 GB；驱动 580.173.02；板卡功耗上限 450 W。
- 候选运行时：`/data/tools/vllm28-env`，vLLM 0.28.0，PyTorch 2.13.0+cu130，`torch.version.cuda=13.0`。
- 目标：当前生产 `Qwen3.8-27B-coding-v1.1-W4A16` AutoRound/compressed-tensors 检查点，包含 INT8 embed/lm_head。
- 测试卡：仅 GPU2。生产 llama.cpp/vLLM 卡未重启、未修改。

## 兼容性结果
原生 vLLM 0.28.0 加载生产检查点失败，原因是打包的 INT8 embedding 没有按量化配置构造（`embed_tokens.weight_packed` 没有目标参数）。

在沙箱 overlay 中，将现有 `inference/vllm/patches/qwen3_5-embed-quant.patch` 逻辑应用到 Qwen3.5 `VocabParallelEmbedding` 后，目标模型可以加载。补丁 SHA256：`0a1b9ca06798c1aef582995de5a0beb3ad9a22a54cdbd2361986563a9c7a980e`。

结果：**仅目标加载兼容性 PASS**。模型成功加载 7/7 个权重分片，并通过优化编译／CUDA Graph 路径达到 API Ready。

## 首轮可比的仅目标测量
测试工具：现有 `inference/vllm/bench/ulmus_validate.py`，p565/g512 流式 decode 夹具，temperature 0、seed 4242，测量三次；未启用投机解码。

- decode：57.5033／57.9550／57.9536 tok/s
- decode 中位数：**57.9536 tok/s**
- 4K prefill：实际 prompt 4,129 token，**2887.23 tok/s**
- 观测到的近似编译时间：39.5 s；完整引擎初始化约 114 s

测试辅助程序的板卡功耗采样器读取第一张可见 GPU，而不是 GPU2，因此本轮功耗字段无效，已从资格结论中排除。

## 同卡 vLLM 0.27.1/cu129 仅目标基线
随后在 GPU2 上使用当前 0.27.1/cu129 镜像运行完全相同的目标、32K 最大上下文、max-seqs=1、前缀缓存设置和 p565/g512 夹具，同样未启用投机解码。

- decode：57.6851／57.6894／57.6843 tok/s
- decode 中位数：**57.6851 tok/s**
- 4K prefill：实际 prompt 4,129 token，**2887.34 tok/s**
- 引擎初始化：总计约 163 s；torch.compile 约 86.9 s

相对于 0.28/cu130，0.27.1/cu129 的 decode 从 57.6851 变为 57.9536 tok/s，变化为 **+0.47%**；prefill 基本相同。实质改善是启动／编译时间：约 163 s 降至约 114 s。

## 原生 DFlash2／cu130——第 1 次启动资格结果
vLLM 0.28 已原生包含 `DFlash2DraftModel` 和 V2 DFlash2 speculator，因此没有整体迁移 0.27.1 的 DFlash2 backport。生产重校准 W4A16 drafter 在 0.28/cu130 沙箱中暴露出两个已证明的兼容性缺口：

1. compressed-tensors W4A16 的 `qkv_proj` 没有 dense `.weight`；DFlash 上下文 K/V 预计算需要沿用现有的打包量化 K/V 行反量化逻辑。
2. DFlash2 candidate selector 的 `flashinfer.top_k` JIT 在 cu130 环境因 CCCL／工具包头文件不匹配失败，因此本线路强制使用 `torch.topk`。

加上这两个最小兼容性改动和现有 Qwen3.5 量化 embedding 修复后，0.28/cu130 成功加载目标 7/7 分片及 recal drafter 1/1 分片，捕获目标和 DFlash2 CUDA Graph，并达到 API Ready。

32K 纯文本、第 1 次启动、p565/g512 资格结果：decode 中位数 **141.6137 tok/s**（141.7234／141.6137／141.5426），4K prefill **2883.92 tok/s**。benchmark 增量记录 236 个 draft step、1652 个 draft token 和 530 个接受 token（**32.08% draft-token acceptance**），接受位置为 175／116／89／58／35／30／27。原始数据：`dflash2-cu130-boot1.json`。

这只是资格数据，还不是生产结论：当前形制是 32K 纯文本，必须通过独立新启动后，才能在生产 245760 上下文／视觉形制比较。辅助程序的功耗字段仍无效，因为采样的是 GPU0；板卡功耗另行处理。

## 新启动可重复性门
同一 32K 纯文本 DFlash2 形制在 GPU2 上独立启动三次，decode 中位数为 **141.6137／141.6538／141.6070 tok/s**。均值 **141.6248 tok/s**，样本标准差 **0.0253 tok/s**；总范围 **0.0468 tok/s，即均值的 0.033%**。三次确定性夹具的 draft-token acceptance 均为 **32.082%**。

结论：**PASS——本次 3 次启动窗口未观察到启动级双峰。** 这关闭了当前 32K 形制的 0.27 时代启动模式疑虑，但不能证明 245760 生产形制。原始文件：`dflash2-cu130-boot{1,2,3}.json`；汇总：`dflash2-cu130-fresh-boots-summary.json`。

## 原生长上下文容量门
同一 0.28/cu130 原生 DFlash2 线路以精确生产目标 `max_model_len=245760` 启动，仍为纯文本且未启用 KVarN。引擎在 KV-cache sizing 阶段失败：需要 **20.36 GiB** KV cache，但只有 **4.91 GiB** 可用。vLLM 估计最大模型长度为 **43,264 token**。

随后直接测试该估计值。`max_model_len=43264` 达到 API Ready；vLLM 分配 **43,545 个 KV-cache token**，对 43,264-token 请求报告最大并发 **1.01x**。因此 **43,264 是已观察到的原生 KV 启动上限**，不只是估计值。由于配置上限以上只剩 281 个 KV token，不建议把它作为生产日常设置。

结论：模型本身没有失去上下文能力；缺少的是 0.27 生产栈的 KVarN／混合 KV 内存路径。没有迁移该能力，原生 0.28/cu130 无法在单张 24 GB 4090 上接近 245760。原始汇总：`native-long-context-capacity.json`。

## 解释
57.95 tok/s 是**仅目标的引擎／运行时数据**，不能直接与当前约 130 tok/s 的生产数字比较，因为生产数字启用了 DFlash2 k=7。同卡 A/B 表明，单独升级 CUDA13／vLLM 0.28 并不能相对于 0.27.1/cu129 带来实质单流 decode 增益；下一项决定性测试是 0.28/cu130 原生 DFlash2。

替代基线分为两层：
1. vLLM 0.27.1/cu129，同一目标，仅目标，同一夹具。
2. vLLM 0.28/cu130，完成所需补丁迁移后的生产形 DFlash2 配置。

FastLLM 必须击败最强可部署的 vLLM 结果，不能只击败旧的 0.27.1/cu129 线路。

## 当前任务／下一任务
- 已完成：vLLM 0.27.1/cu129 同卡仅目标基线；decode 与 0.28/cu130 基本持平（0.28 为 +0.47%），而 0.28 启动／编译明显更快。
- 已完成：原生 DFlash2 + recal W4A16 兼容性及 3 次新启动可重复性门；32K decode 均值 141.625 tok/s，总启动范围仅 0.033%，未观察到双峰。
- 已完成：原生长上下文容量门。245760 需要 20.36 GiB KV、可用 4.91 GiB；43,264 是经过验证的原生 KV API-ready 上限（43,545 KV token，1.01x 并发）。
- 当前：将最小 0.27 KVarN／混合 KV 能力移植到隔离的 0.28/cu130 overlay；第一批门是 import／配置／KV-init，不是性能。
- 下一步：恢复 245760 容量，再认证前缀缓存、质量和稳定性，并以最强可部署 vLLM 结果作为 FastLLM 替代阈值。
- 本报告未授权任何生产配置变更。

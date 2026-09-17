# KVarN KV cache：移植到 vLLM 0.27.1

[KVarN](https://github.com/huawei-csl/KVarN)（华为 CSL，Apache-2.0）是一种 KV cache 压缩方案：使用 Hadamard 旋转、迭代方差归一化，并以每 128-token tile 的 4-bit key／2-bit value 进行压缩。它原本作为 vLLM 0.23.0 分支中的原生 attention backend 提供。本目录将该 backend 移植到本仓库使用的 vLLM 0.27.1，仅支持 dense（非 MLA）路径。移植最初来自单卡 RTX 3090 上游栈，已在 RTX 4090 上完成资格评估；保留测量见根目录 README。

## 目录内容
- `files/vllm/...`：KVarN 模块，包括 backend、Triton kernel、配置和 Sinkhorn 参考实现；从 KVarN 复制并适配到 0.27.1 backend API，每处改动以 `# port(0.27.1)` 标记，上游 KVarN 头部保留。
- `kvarn-0.27.1.patch`：上游 vLLM 需要的七处小补丁，用于识别新的 `kvarn_*` cache dtype，包括 cache dtype 字面量、dtype 映射、backend 注册与优先级、`KVQuantMode.KVARN`、attention 层 KV-cache spec 分支和混合模型页面对齐分支。
- `install.sh`：将模块复制到 `venv/lib/python3.12/site-packages/vllm` 并应用补丁，可安全重复执行。

## 移植注意事项
- 0.27.1 会在 `kv_quant_mode` 为 `NONE` 的 spec 上调用 `get_kv_cache_shape(..., cache_dtype_str=auto)`；KVarN 的 shape 取决于 preset，因此移植增加 `KVQuantMode.KVARN`，并通过复用的 `TQFullAttentionSpec` 传递。缺少该处理会在 KV-cache 初始化时退出。
- impl 到 builder 的连接使用 `get_layers_from_vllm_config`，而不是 KVarN `attention.py` 中的 `impl.layer_name` 修改，并增加 owner registry，避免 MTP draft 层被两个 builder 重复清空。
- 在 `profile_run` 期间通过 `attn_metadata=None` 的 forward 实例化池，使 vLLM 内存 profiler 正确计费，不需要修改 `gpu_worker.py`。
- 每 token slot 默认不补齐到 2 的幂；设置 `KVARN_POW2_SLOT=1` 可恢复该行为。当前 head_dim 256 时为 840 B/token/layer，而不是 1024（fp8 为 2048）。
- 混合对齐使 attention block 为 2048 token，页面必须匹配 1.63 MB 的 Gated-DeltaNet 页面；vLLM 将其拆成 128-token kernel tile，KVarN 的 `tile == kernel block` 不变量成立。
- 小型稳健性修复包括：对全 mask chunk／全空 split-K 行增加 NaN 防护；禁止 packed-KV kernel 按上下文重复编译；将 verify-plan padding 清零以适配 CUDA Graph 重放。
- 未移植：MLA 路径、`TQSlidingWindowSpec`（当前没有 sliding-window 层）以及 Gemma-4 配置修改。

上游 RTX 3090 测量表明：262K 上下文可以容纳（4 slot 时池容量 420K token，而 fp8 约 200K）；4K 至 240K 的 needle 测试正确；困惑度增加 0.16%；100K 上下文 decode 比 fp8 慢约 20%；MTP 可用；短请求吞吐较低，因为 2048-token block 使每个请求的成本高于 fp8 的 800-token block，且 prefill flush 会增加耗时。

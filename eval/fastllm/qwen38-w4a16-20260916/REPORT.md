# FastLLM Qwen3.8 W4A16 资格评估——2026-09-16

状态：**已归档／未选择部署**。本目录作为未来回归基线保留，不是生产配方。

## 冻结身份
- 上游 FastLLM 固定提交：`74d36383312421e8316501aa46f7c002c8e490d9`。
- 资格评估运行时：CUDA 13／SM89 源码构建，并对 `embed_tokens` 与 `lm_head` 执行本地 W8-group128 加载器探针。
- 当前源码原生库 SHA256：`e29752af9e353bd39eb2adf6202f57b437ad29215c94506c07198d173be3f445`。
- 稳定版 `ftllm==0.1.8.2` 原生库 SHA256：`0d386f46b4e7ee8b9e5f3f57cdf10e823a31ae5a9097dadc4ccf278b6284f857`。
- 模型：Qwen3.8-27B coding v1.1 AutoRound W4A16，与 vLLM 资格评估使用同一目标。

## 当前源码的有效发现
| 形制 | 结果 |
|---|---|
| TP1 8K 冒烟 | W8/F16 加载器探针后 PASS |
| TP1 128K FP4 KV | 预热阶段 OOM；不可部署 |
| TP2 128K C1 | PASS；127,011 token 随机五针为 5/5 |
| TP2 127K TTFT | 119.95 s；decode 约 55.0 tok/s |
| TP4 128K C1 | PASS；127,011 token 随机五针为 5/5 |
| TP4 127K TTFT | 88.93 s；decode 约 73.7 tok/s |
| TP3／TP5／TP6 128K C1 | 在 I32／allocator 加载路径失败 |
| TP2／TP4 131,200 token | FAIL；已证明的服务窗口上限为 131,072 |
| TP2 max_batch=2，64K | 服务启动阶段失败 |

## 决策
FastLLM 未被选为 vLLM 的替代方案。在该检查点和 8×RTX 4090 PCIe 主机上，测试源码线路需要本地加载器改造；只有 TP2／TP4 到达 128K 正确性门，TP3／TP5／TP6 失败，超过 128K 的形制未启动；同时 TP4 使用四张 GPU，而 127K TTFT 仍略慢于已归档的单卡 vLLM 0.27／0.28 参考。

## 证据卫生
`raw/fastllm-raw-snapshot.tar.gz` 按字节保留原始实验文件。部分中间命令误解析到稳定 Wheel 而不是源码探针，这些运行记录在 `INVALID-RUNTIME-CONTAMINATION.txt` 中，不得用于当前源码结论。`RESULTS.json` 保存已接受的汇总结果。探针源码历史保存在 `source/fastllm-probe-source-history.tar.gz`；102 MB 原生二进制有意不提交。

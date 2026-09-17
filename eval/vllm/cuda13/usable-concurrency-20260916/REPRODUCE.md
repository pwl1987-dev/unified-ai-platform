# 复现 vLLM 0.27／0.28 资格评估

本套文件用于在不依赖原始沙箱的情况下复现 RTX 4090 对比。

## 前置条件
- NVIDIA RTX 4090 24GB；0.28 线路使用的驱动必须兼容 CUDA 13.0。
- 目标模型和 DFlash2 检查点必须与 `repro/manifests/model-sha256.txt` 匹配。
- 0.28 使用 Python 3.12、`venv` 和 `patch`；0.27 使用 Docker 和已归档的 0.27 镜像。
- 不同并发形制之间不得复用编译缓存。

## 验证模型身份

运行任何基准前，先将检查点文件与 `repro/manifests/model-sha256.txt` 比较。`model-paths-reference.txt` 只记录原始路径作为参考，其他主机可以使用不同路径。

## 构建 0.28/cu130 环境

在仓库根目录执行：

```bash
VENV=/opt/qwen-vllm028 \
  eval/vllm/cuda13/usable-concurrency-20260916/repro/setup_vllm028.sh
```

setup 脚本会安装锁定的软件包，执行 `patch --dry-run`，应用 `inference/vllm/build/cu130-driver580/vllm028-kvarn-dflash2-w4a16.patch`，并导入 KVarN + DFlash2 补丁代码。

## 启动任一测试线路

设置精确的检查点目录，然后只启动当前要测试的线路：

```bash
export TARGET_DIR=/path/to/exact/target
export DRAFT_DIR=/path/to/exact/dflash2
GPU=2 PORT=19637 MAX_SEQS=1 VENV=/opt/qwen-vllm028 \
  eval/vllm/cuda13/usable-concurrency-20260916/repro/start_vllm028.sh
```

0.27 使用 `start_vllm027.sh`；如果归档镜像使用其他本地标签，设置 `IMAGE`。两个启动器都固定 `max_model_len=245760`、KVarN k4v2_g128、KV=4.82GB、DFlash2 k=7、CG=8、前缀缓存、mamba 对齐和 2048 个 batched token。

## 运行证据探针

容量／接入测试使用 `long_concurrency_probe_v4.py`；长上下文准确性使用 `captured/long_multineedle_probe_v2.py`。每个请求使用唯一 cache salt，并在原始证据中保留精确的 prompt／token 目标。

主要决策点是 C1 224K／240K、C2 128K，以及约 127K／223K／239K 的随机五针准确性。约 4K 的 C4／C6／C8 数据只用于确定物理常驻上限。

## 证据规则

`raw/valid/` 为权威证据。`raw/invalid/accuracy-v1/` 有意保留，但不得用于结论。`raw/historical/` 记录早期实验／失败。`SUMMARY.json` 是机器可读汇总，`REPORT.md` 是当前解释。

FastLLM 必须使用相同的上下文、准确性、TTFT 和稳定性门，之后才可以被视为替代方案。

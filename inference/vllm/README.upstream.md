# NVIDIA RTX 4090 本地推理

> [返回项目首页](../../README.md) · [返回上级目录说明](../README.md)

本目录记录 Qwen3.8-27B 在单张 24 GiB RTX 4090 上经过质量门控的优化结果。选定的完整窗口服务在启用视觉、自动前缀缓存和完整 262,144-token 模型上下文时可维持 **136.47 tok/s**。匹配的 BF16 基准形制 decode 为 **178.72 tok/s**，32,817-token 冷 prefill 为 **2,299 tok/s**；此前 llama.cpp 形制为 62.61 tok/s。

选定目标是 Huihui 的 abliterated 模型，量化版本为 `ababaka/Huihui-Qwen3.8-27B-Abliterated-W4A16-AutoRound`，revision 为 `c20530baefe3e77ccfc6891c2b50cce7ea28bf1e`。本地 fast variant 使用已完成资格认证的 int4-GPTQ head／MTP 资产，revision 为 `124c14e7e8c7d2f5402933b9af368e772a9fcf0c`；两者源张量逐字节一致。DFlash2 W4A16 revision 为 `4d30ec736ffc6b8688dc2ae2b502d9b48bdec279`。stock target 仅作为回滚和历史基准保留。

实现基于 `syv-ai/qwen38-27b-rtx3090` 的提交 `dfee877366ff0db341d5d685784154f17b3a2f64`，配套可复现的 CUDA 12.9 镜像和 RTX 4090 专用资格配置。

## 结果
服务在未启用认证的 `0.0.0.0:19622` 上提供 `qwen3.8-27b`。只能在可信网络中使用。

| 选定设置 | 值 |
|---|---|
| GPU | 单张 RTX 4090，24 GiB，功耗上限 280 W |
| 目标 | Huihui Qwen3.8-27B Abliterated W4A16 |
| Speculator | DFlash2 W4A16，k=7 |
| 上下文 | 服务端 262,144；OpenCode 为 245,760 输入 + 8,192 输出 |
| KV cache | KVarN K4V2，报告 272,781 token |
| 必需特性 | 视觉和自动前缀缓存 |
| API | OpenAI 兼容，端口 19622，无 key |

## 边界与约束
- Ulmus 使用驱动 `550.163.01` 时，不得使用上游 CUDA 13 预构建镜像；`docker/Dockerfile.cu129` 固定官方 vLLM 0.27.1 CUDA 12.9 wheel。
- 不得改变本轮测试的 280 W GPU 功耗上限。
- 视觉和自动前缀缓存是必需特性。所有 profile 设置 `VISION=1`、`VISION_OFFLOAD=1` 和 `PREFIX_CACHE=1`。视觉塔常驻会减少显存余量并导致组合 32K／cache 工作负载失败，因此稳定整体折中是 offload。
- Huihui 与 stock 检查点的 333 个视觉张量已直接比较且逐字节相同，目标切换后 A/B 结论仍可用。
- endpoint 有意在所有 Ulmus 接口以无 API key 方式发布，仅适用于可信局域网；不得将此端口转发到互联网边缘。
- `models/`、`cache/`、profiles、源码和结果均保留在本目录下。

## Profiles
`compose.yaml` 默认将 `MODEL` 设置为 `/app/models/Huihui-Qwen3.8-27B-Abliterated-W4A16-AutoRound-fast`；显式覆盖 `MODEL` 只用于受控 A/B。

`max` 是已部署 profile：DFlash2 k=7、KVarN K4V2 KV、单请求 slot 和完整 262,144-token 服务端上下文。`fast` 是匹配的性能基准，使用 BF16 KV 和 65,536-token 上下文。`long` 牺牲冷 prefill 速度，使用 131,072-token INT8 KV 上下文。`mtp-long` 是 150,000-token FP8-KV 原生 MTP 控制形制。`huge` 是早期 245,760-token KVarN 形制。两个 KVarN profile 都是有损 cache；`max` 接受该测量折中，以保留完整原生窗口。

启动方式：
```bash
git clone https://github.com/AnnoyingTechnology/nvidia-4090-llm-inference
cd nvidia-4090-llm-inference
cp profiles/max.env .env
sudo docker compose build
sudo docker compose up -d
sudo docker compose logs -f qwen
```

首次启动会下载固定版本的 Huihui 目标、组装本地 fast variant、获取 DFlash2 sidecar，并编译 CUDA／Triton kernel。构建、模型和编译缓存会持久化在本目录。`compose.yaml` 声明模型仓库和不可变 revision，新的 models volume 不会静默回退到 stock target。

验证不可妥协的特性，并在 `/health` 就绪后从主机采集比较单元：
```bash
python3 bench/ulmus_validate.py --benchmark --profile max --prefill-target 32768
```

## 已认证结果（2026-09-03）
| Profile | KV／上下文 | p565/g512 decode | 冷 prefill | 视觉 | 前缀缓存 |
|---|---|---:|---:|---|---|
| `max`（当前） | KVarN K4V2／262,144 | 136.47 tok/s | p32,817 时 2,230 tok/s | PASS | PASS，复用 32,640 token |
| `fast`（文章基准） | BF16／65,536 | 178.72 tok/s | p32,817 时 2,299 tok/s | PASS | PASS，复用 33,600／34,231 token |

`max` 的 decode 中位板卡功耗为 278.3 W，保留的 `fast` 文章运行记录为 278.8 W。当前 `max` profile 通过 `bench/api_smoke.py` 的全部 12 项请求级检查。DFlash2 k=5 较慢，为 129.02 tok/s；k=3 更慢，为 124.03 tok/s，且失败于前缀缓存 canary，因此继续选择 k=7。

当前机器可读结果位于 `results/huihui-fast-32k-qualified.json`、`results/huihui-max-32k-qualified.json`、`results/huihui-max-exact-boundary.json` 和 `results/huihui-max-api-smoke.txt`。k=3、k=5 的否决证据也与其并列保留；视觉 residency A/B 为 `results/vision-offload-ab.json`。

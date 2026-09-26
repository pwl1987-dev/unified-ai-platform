# CONTROL-PROD Reality Reconciliation（2026-09-26）

> 只读核对，零修改。机器证据见 `control-prod.json`；原始 /props 见 `control-prod-props.json`。
> 本文件 = 事实 + 与既有认知的差异清单。

## 1. 当前真实业务 llama.cpp 是什么

**双副本 llama-server，每副本 1×4090，OpenResty :8000 会话粘滞 LB 入口。**

| 项 | 值 |
|---|---|
| 容器 | `qwen27b`(GPU0, 127.0.0.1:8081)、`qwen27b-r1`(GPU1, 127.0.0.1:8082) |
| 镜像 | `llama-server:cuda12.4-b10715`（digest `sha256:cc0782…5fa`，2026-08-31 构建） |
| 基础镜像 | `nvidia/cuda:12.4.1-runtime-ubuntu22.04`（容器内 CUDA Runtime 12.4.1） |
| 模型 | `/data/models/Qwen3.8-27B-coding-v1.1-iq4xs.gguf`（15.30GB，IQ4_XS 4.25bpw，sha256 `397a76…87fe`） |
| 草稿 | DFlash2 Q4_K_M sidecar（1.18GB，`--spec-type draft-dflash --spec-draft-n-max 7`） |
| ctx / parallel | `-c 262144 -np 1`（每副本 1 slot；双副本=系统级 C2） |
| KV | K=q4_0 V=q4_0；草稿 KV q8_0 |
| FA | `-fa on`；`--cache-reuse 2048`；`--jinja` |
| 采样默认 | temp 1.0 / top_k 20 / top_p 0.95 / min_p 0.05（props 实读） |
| 显存 | 23142 / 23108 MiB（两卡 ~94%） |
| 架构 | qwen35 混合线性注意力（16/64 全注意力层 + 48 GDN 层），GQA 24Q/4KV head_dim 256，原生 VL 词表，内嵌 MTP-1（nextn=1） |
| 启动 | docker compose `/data/compose/qwen27b/docker-compose.yml`，restart unless-stopped，无容器级 healthcheck（LB 层探测 /slots） |
| 健康 | :8000/:8081/:8082 health 全 200（08:28 实测） |

## 2. 宿主与 Runtime 链路

- Host Driver **580.173.02**，Driver CUDA capability **13.0** —— 但宿主**无 CUDA Toolkit、无 nvcc**。生产链路 = R580 → NVIDIA Container Toolkit 1.20.0 → 容器内 CUDA 12.4.1 runtime → llama.cpp b10715。
- CPU 2×Xeon Gold 6530（64C/128T），RAM 503GiB，/data 7TB RAID（5.1TB 可用）。
- b10715 二进制自报 `build 0, commit unknown`（构建时未注入元数据）；exact 源码树 `/data/build/llama.cpp-new`（无 .git，随 `llama-src-new.tar.gz` 而来）。**官方 upstream 精确 commit 无法从二进制反推**，RUNTIME-CURRENT 即以本地镜像 digest 为 Authority。
- 网络：`huggingface.co` 直连不通，**hf-mirror.com 可达**（API 已验证）。下载一律走 HF_ENDPOINT=https://hf-mirror.com。

## 3. 与既有认知（AGENTS/文档）的差异（Reality > 笔记）

1. 用户级 AGENTS.md 写"vLLM 4 副本 GPU0-3 @:8000" —— **过时**。现实：llama.cpp 双副本 GPU0/1 挂 :8000 LB；GPU5 上另有独立 vLLM Qwen3.5-2B（:8010，工具服务），与 :8000 无关。
2. 工作区 AGENTS.md 写"空闲池 GPU4/5/7" —— **过时**。现实空闲：**GPU 2/3/4/6/7**（GPU5 被 vLLM 占用 20GB）。
3. 历史性能口径：分析文档 2026-08-31 修正为单流 ~72 tok/s（旧"100-113"废弃）；195K 处 ~28-35 tok/s（-60%）。本轮 A/B 以本次实测为准。
4. 生产模型已从 Heretic-Ara 换成 coding-v1.1（compose 备份链 20260903-codingv1），文档部分章节仍是旧模型。

## 4. 测试期间禁动清单（本轮已遵守并将持续遵守）

GPU0/1 全部进程；`qwen27b*` 四容器；/data/models 下生产文件（只读挂载给测试容器）；宿主 Driver；GPU5 的 vLLM(:8010)；生产 compose/lb/mon 配置。测试一律用 GPU 2/3/4/6/7 + 端口 18101+，会话收尾 GPU2-7 清场并复查 :8000 = 200。

## 5. 结论

CONTROL-PROD 已完整画像并可作 Runtime A/B 的固定模型基准（模型+草稿均本地在盘，sha256 已固化）。RUNTIME-CURRENT 可无损复现：同一镜像 digest 拉起隔离容器即可，不触碰生产。

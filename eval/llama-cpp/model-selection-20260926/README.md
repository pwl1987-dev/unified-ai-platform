# llama.cpp Model Selection 2026-09 — Evidence Bundle

任务：为未来业务选定 llama.cpp 主模型 + 冻结 Production Runtime Profile（编程/Agent > 长上下文 > 中文写作 > 结构化输出 > 视觉 > 吞吐）。

## 结论（TL;DR）

1. **Runtime 冻结 = `llama-server:cuda12.4-b10715`**（与生产同二进制）。官方 CUDA13 镜像在 R580(CUDA13.0) 上全线不可启动；本地 CUDA13.0-sm89(master) prefill 回调 → 弃。官方 CUDA12.8 decode 更快、prefill 略慢，留档待拍板。
2. **PRIMARY（技术胜者）= Swift 1.5 Q5_K_M @ 2×4090 + 256K**（编程/长码/长上下文第一；needle 全深度 100%）；**LONGCTX-ECONOMY = Swift 1.5 GSQ IQ3_S-mtp @ 1×4090 + 256K**（思考 token 最省、C8 134 tok/s）。
3. **License 双双为 Swift Open License v1.0（$1M 收入门槛）→ 部署前必须人工拍板**；Apache 回落方案 = ISTA GSQ IQ3_S-mtp（有默认模板无限思考缺陷，见 PRODUCTION-RECOMMENDATION 附录 A）。
4. FA=on 强制（off ≥131K 不可部署）；KV=q4_0（vs f16/q8 差 <3%）；MTP decode +34~37% 换 prefill -17~-25%（按负载取舍）；CPU mmproj 可用（省 1.16GB，+0.6s/图）。

## 目录

| 路径 | 内容 |
|---|---|
| `CONTROL-PROD-REALITY.md` + `control-prod.json` | 生产只读核对（含与文档差异清单） |
| `environment.json` | 宿主/GPU/驱动/Docker 全量快照 |
| `runtime-matrix.json` / `runtime-selection.json` / `runs/runtime-ab/` | Runtime A/B（3 运行时 × 冷启动×2 × 1K-256K 梯度 × JSON/tool 冒烟 × 30min soak） |
| `artifact-matrix.json` | 四仓 exact revision/文件/量化/许可证/mmproj |
| `licenses/` | License Gate + Swift Open License 全文 |
| `runs/stage1/` | 四模型统一筛选（探针机器判分 + 全量容器日志） |
| `runs/longctx/` | needle 电池（10-98% 深度 × 单/多/干扰 × 32K/128K/256K） |
| `runs/long-code/` | 真实仓库 8 题（grep 判分）+ 合成工程 4 题 + 可执行补丁 |
| `runs/coding/` | 13 题多语言（python/bash/sql/c 结构验证 + exec 权威） |
| `runs/structured-output/` `runs/agent/` `runs/writing/` | 结构化输出 / 模拟工具 Agent(含 8/16/32 轮) / 中文写作机器度量 |
| `runs/vision/` | ISTA 与 Swift15 mmproj × CPU/GPU（业务图三题） |
| `runs/opt/` | KV(f16/q8/q4) × FA(on/off) × spec(none/mtp/dflash/ngram) 矩阵 |
| `runs/concurrency/` | C1/C2/C4/C8（-np 8 @256K） |
| `runs/gpu/` | Q5/Q6 双卡 256K 缩放 |
| `runs/soak/` | 候选 30 分钟持续负载 |
| `model-profiles.json` | 两个 Profile 的完整部署指纹 |
| `summary.json` / `pareto.json` | 全轴汇总与硬门 |
| `PRODUCTION-RECOMMENDATION.md` | 40 问全答 + 最终裁决 + 部署 YAML |
| `repro/`（仓库副本） | compose/build/下载/全部 runner 脚本 + uv.lock |

## 复现要点

- 全部测试走 `ops/llama-cpp-model-lab/docker-compose.yml`（每容器独立 compose project、独立端口 181xx、GPU 白名单 2/3/4/6/7、生产目录只读挂载）。
- harness：`uv run python <suite>.py <image> <gpu> <model> <key>`（CPU-only，OpenAI 兼容 HTTP；uv.lock 冻结）。
- 长上下文探针必须给服务端模板计数留 ≥4K token 余量（客户端 /tokenize 偏低 ~2K）。

## 铁律遵守记录

- 生产 llama.cpp（GPU0/1、:8000/:8081/:8082、lb/mon）零触碰；GPU5 vLLM(:8010) 零触碰；宿主 Driver 未动。
- 模型目录对测试容器一律 `:ro`；证据独立目录；端口无冲突（181xx）。
- 本目录为**本地原始证据**（含内网信息）；公开仓副本经 8 规则脱敏（`export_repo.py`，提交前扫描零命中）。

# media/ · 媒体生产线

> [返回项目首页](../README.md)

媒体线是新闻结构化和多模态生产的执行层：素材入库 → 镜头分割 → ASR／词级对齐 → 人脸／OCR → 语义拆条 → 检索 → EDL 自动成片。

## 模块导航

| 模块 | 入口 | 定位 |
|---|---|---|
| 一键编目 | [`news_pipeline/`](news_pipeline/) | 批次 I，P0-P4，节目→故事→镜头→词级时间轴 |
| 多模型服务 | [`serve/`](serve/) | ASR、文本、视觉、视频模型启停 |
| 检索与视觉周边 | [`services/`](services/) | embed、rerank、VL-8B 三容器 |
| 视频生成 | [`comfyui-minimax-h3/`](comfyui-minimax-h3/) | ComfyUI + MiniMax-H3，GPU2/3 按需启停 |
| 实测文档 | [`docs/`](docs/) | 模型选型、能力矩阵、素材清单和结果 |

## 当前能力摘要

- 编目管线：11 阶段 DAG，原子缓存、Run Lock、GPU 守卫和阈值唯一真源。
- 边界质量：F1 约 0.94；LLM 作为证人，不作为唯一主权判定者。
- 方言 ASR：FireRedASR2-AED 主力，Qwen3-ASR-1.7B 作为服务化路线。
- 视频生成：MiniMax-H3 双卡 FP8，支持 turbo LoRA 路线。

详细测量和选型以 [`docs/RESULTS.md`](docs/RESULTS.md) 与 [`docs/MODEL-PICKS-2026-09.md`](docs/MODEL-PICKS-2026-09.md) 为准。

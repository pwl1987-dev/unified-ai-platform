# training/ · 后训练与 LoRA 工具链

> [返回项目首页](../README.md)

本目录与推理运行时分离，保存 QLoRA 训练、MTP/drafter 实验以及 LoRA→GGUF 转换补丁。

## 模块导航

| 模块 | 入口 | 内容 |
|---|---|---|
| QLoRA 训练 | [`train/`](train/) | ms-swift、DeepSpeed、数据转换、断点续训和训练记录 |
| llama.cpp 转换 | [`llamacpp/`](llamacpp/) | GDN `out_proj` 列重排与 LoRA→GGUF |
| 训练日志 | [`train/TRAIN-NOTES.md`](train/TRAIN-NOTES.md) | 训练六坑、驱动升级和完整执行记录 |

## 已保留产物

- 4×4090 ZeRO-3 + NF4 double-quant，稳态显存约 21.6G／卡。
- `checkpoint-4840` → `final-lora.gguf`（f32，934M）／`final-lora-q8.gguf`（248M）。
- 热挂使用 rsLoRA 缩放补偿：`--lora-scaled <adapter>:5.657`（√32）。

## 约束

模型权重和大型产物不入库；训练结果必须绑定数据版本、配置、模型身份和原始证据。详细记录见 [TRAIN-NOTES.md](train/TRAIN-NOTES.md)。

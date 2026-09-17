# model/ · 模型结构与模板

> [返回项目首页](../README.md) · [返回推理总览](../inference/README.md)

| 文件 | 作用 |
|---|---|
| `config.json` | qwen3_5 混合架构定义：64 层中 16 层全注意力、48 层 GDN |
| `chat_template.jinja` | 对话模板和 thinking／tool 相关格式 |
| `generation_config.json` | 默认生成参数 |

词表大小为 248,320，包含 1 层 MTP 配置。权重本体不入库；量化和打包后的目录结构见 [vLLM 优化日志](../docs/VLLM-OPTIMIZATION.md)。

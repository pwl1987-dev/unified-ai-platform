# ops/ · 机器级运维与监控

> [返回项目首页](../README.md)

本目录提供与具体推理引擎无关的 GPU 监控、功耗控制、噪声模式和启动自检。

## 模块导航

| 模块 | 入口 | 说明 |
|---|---|---|
| 监控 | [`mon/`](mon/) | 2 秒粒度 GPU、slot、vLLM 和 24h 历史 |
| 功耗 | [`scripts/gpu-power.sh`](scripts/gpu-power.sh) | day／quiet／night 三档功耗墙 |
| 噪声模式 | [`scripts/noise-mode.sh`](scripts/noise-mode.sh) | 白天软摘除副本，晚间恢复 |
| 启动自检 | [`scripts/bootcheck.sh`](scripts/bootcheck.sh) | 驱动、容器、LB 和 ComfyUI 探活 |

## 运维规则

- 生产 GPU 和端口默认不可动；实验先做 GPU、进程、端口和显存预检。
- 功耗墙、GPU UUID、模型和服务状态都要写入实验证据。
- `pkill -f` 必须避免自匹配；杀服务前先确认 PID。
- 长稳实验结束后清理实验进程，并确认生产健康检查返回 200。

# METRICS-SCHEMA — 指标定义、公式、时间窗与旧字段映射

本文件与 `repro/schema/{metrics,raw-events,manifest}.schema.json` 同步；公式以本文件为权威，
schema 做结构校验，`tools/test_metrics_synthetic.py` 用合成时间戳验证公式实现。

## 0. 时钟与时间点定义

所有客户端时刻用 `time.monotonic_ns()` 采集，同时记录对应 UTC（`time.time_ns()`）。
**禁止用墙上时钟算差值。**

| 时刻 | 定义 |
|---|---|
| `request_start` | 请求线程通过起跑 barrier 后、发起 HTTP 请求前（monotonic） |
| `first_header` | 收到 HTTP 响应头（headers received） |
| `first_token` | 第一个携带非空 `delta.content`（或 usage 外有效生成内容）的 SSE 事件 |
| `token_ts[i]` | 第 i 个生成 token 的到达时刻（内存记录，结束后批量落盘） |
| `last_token` | 最后一个生成 token 的到达时刻（不含 `[DONE]`/usage 事件） |
| `batch_start` | barrier 释放时刻（并发组公共起点） |
| `batch_end` | 组内所有请求的 `max(last_token)`（或错误终止时刻） |

## 1. 冻结公式（每请求）

```
ttfb_s                = first_header  - request_start
ttft_s                = first_token   - request_start
e2e_output_tok_s      = output_tokens / (last_token - request_start)
client_observed_decode_tok_s = (output_tokens - 1) / (last_token - first_token)
tpot_s                = (last_token - first_token) / (output_tokens - 1)
```

- `output_tokens < 2` 时 `client_observed_decode_tok_s`/`tpot_s` = `null`，
  `null_reason = INSUFFICIENT_TOKENS`（禁止 0/NaN/Inf）。
- `client_observed_decode_tok_s` 是**客户端观测值**：token 到达时刻含 HTTP/SSE flush、
  socket 与客户端调度抖动，不得宣称等同 engine 内部 decode 速率。
- `output_tokens` 优先取 server `usage.completion_tokens`；client 计数
  （`client_token_count`）独立记录并交叉核对，不一致时该样本标 `COUNT_MISMATCH`。

## 2. 并发聚合（C>1）

```
aggregate_output_tok_s = sum(output_tokens of all requests) / (batch_end - batch_start)
```

- **禁止**用"各请求 tok/s 的平均"冒充 aggregate。
- C4+ 必须 reporting `max_running`（/metrics 采样峰值）并满足驻留有效性 Gate
  （`max_running == C`），否则该 run 标 `NOT_RESIDENT_CONCURRENCY`，aggregate 只作
  非配对观察。

## 3. 分位数口径（两层，禁止混用）

- **样本层**（单 run 内请求/token 数足够多）：TTFT/TPOT/TTFB 报 P50/P95/P99。
- **重复层**（锚点 ×3 run）：只报 `values + median + min + max + spread_ratio`，
  `spread_ratio = (max - min) / median`（稳定性 Gate 用）。**3 个 run 不产生 P95/P99。**

## 4. 采样器统计

`/metrics` 采样（100ms 冻结）与 NVML 采样（500ms 冻结）各自记录：
`requested_interval_ms / actual_interval_ms{min,median,max} / missing_sample_ratio /
max_gap_ms / sampler_exit_code`。missing 定义：gap > 2 × requested。
`sampler_exit_code != 0` 或 `missing_sample_ratio > 0.05` => 该 run INVALID/HARNESS_ERROR。

## 5. 功耗与能效

- NVML 采样按 GPU UUID 关联（禁逻辑 index），记录 draw/temperature/sm_clock/mem_clock/
  throttle_reasons。
- 能量积分 = 请求时间窗内功耗采样梯形积分；tok/J = output_tokens / 能量(J)。
- 三段自检：空闲/预填/decode 功耗须符合物理常识，异常即 INVALID。

## 6. legacy 字段映射（只读历史，禁止新代码使用）

| legacy（dig028 bench_conc.py） | 本 schema |
|---|---|
| `decode_tok_s = completion/wall`（含 TTFT） | `e2e_output_tok_s`（同名口径） |
| `wall_s` | `e2e_latency_s = last_token - request_start` |
| `aggregate_tok_s` | `aggregate_output_tok_s`（本版分母明确为 batch 窗） |
| `detail[i].decode_tok_s` | `e2e_output_tok_s`（口径同上，历史含 TTFT） |

## 7. 状态与分类字段

每个实验目录 `manifest.json`：

```json
{
  "experiment_id": "V28-T1-Q0-KVARN-SD7-MS1-NBT2048-C1-L032K-B01-R01",
  "evidence_class": "staging | valid | invalid | unsupported",   // 目录三分类
  "status": "VALID_PASS | VALID_FAIL | INVALID | UNSUPPORTED | ABORTED | REJECTED",
  "classification_reason": "PERF_GATE_FAIL | OOM | QUALITY_FAIL | SERVER_CRASH | HARNESS_ERROR | ENV_DRIFT | SCHEMA_FAIL | INTERRUPTED | null"
}
```

语义（v2.1 评审钉死）：测量正确但性能未过门=VALID_FAIL；真实 OOM=VALID_FAIL（有效负结果）；
完整验证后被质量/稳定性淘汰=REJECTED；只有测量链路本身损坏才 INVALID。

## 8. 配对（A/B）必要字段

正式差值计算前，`tools/pairing_check.py` 必须核对两侧：
`fixture_sha256 / actual_input_tokens / requested_output_tokens / stop_condition /
sampling_params / cache_state / client_version`。任一不同 => `UNPAIRED_OBSERVATION`，
不得进入正式加速比。

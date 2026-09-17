# drafter/——自蒸馏数据、校准 int4 重量化、MTP 微调与 DFlash2 重量化

> [返回项目首页](../../../README.md) · [返回上级目录说明](../README.md)

本目录包含构建模型单用户 fast variant 的工具：`models/Qwen3.8-27B-W4A16-AutoRound-fast`，Hub 预构建名称为 `syvai/qwen3.8-27b-3090-fast-variant`，由 `prepare/fetch_fast_variant.py` 组装。目录还包含完整的 MTP head 微调流程；微调没有带来实际收益，但负结果有信息价值，而且同一批数据还服务于有效线路。

所有操作都在 serving venv 的 3090 上执行，端到端约需 6 小时 GPU 时间。

## 真正重要的因素（按优先级）
1. **draft-head 词表。** MTP drafter 对 `lm_head` 的 40,960 行切片打分（`prepare/build_draft_vocab.py`）。切片之外的 token 永远无法被 draft，因此必然拒绝并截断链。原始 id 列表覆盖模型实际生成内容的 92.1%，代码覆盖率为 83%；使用模型自身 5.4M token 输出统计的列表覆盖率为 97.5%，代码为 96%。其他条件不变时，greedy 从 98.0 提升到 108.6 tok/s，默认采样从 90.0 提升到 107.4 tok/s。超过 40K 行收益很小，49K 为 98.2%，且实测更慢。
2. **lm_head 和 MTP 模块的 GPTQ 校准 int4。** 最近邻 int4 使 lm_head 困惑度增加 1.5%，KL 为 0.0068，并使 MTP acceptance 下降约 2%。使用 300K 个 hidden state 的 Hessian（`gptq_lm_head.py`）后，lm_head KL 降到 0.0029，PPL 增加 0.6%，GSM8K 仍为 96.5%；`train_mtp.py --dump-hessians` 得到的 MTP Hessian 可保持 acceptance。组合后每个 decode step 减少约 1.8 ms，greedy 从 108.6 提升到 118.8 tok/s。
3. **MTP head 微调：不值得。** 将目标模型自身分布蒸馏给 drafter，在 draft vocab 上计算 KL，展开 depth-2 链，使用 7M token、1 个 epoch；朴素指标看似变好，但只在 response token 上与真实 next token 比较时，top-1 agreement 不变（0.685→0.685），vLLM acceptance 仍在噪声范围内。KL 收益主要来自 prompt token 以及真实 token 不在 draft vocab 的位置。`train_mtp.py --eval-only` 配合 `--depths 4` 可打印与 vLLM 一致的 greedy 链模拟，原始 head 为 2.5 对 2.6 tok/step。

## Pipeline
```bash
V=venv/bin/python
$V drafter/collect_prompts.py                 # 6.8k prompts，多个公开数据集
VLLM_MARLIN_INPUT_DTYPE=int8 VLLM_MARLIN_INT8_INCLUDE_RE=mlp $V drafter/gen_data.py   # 2.2 h，5.4M 输出 token
$V drafter/capture.py                         # 1.7 h，保存每个 token 的 hidden state
$V drafter/train_mtp.py --out drafter/runs/e --eval-only 1 --draft-ids prepare/draft_vocab_ids.json \
     --max-seqs 400 --val-frac 0.4 --depths 2 --dump-hessians drafter/runs/e/mtp_hessians.pt
$V drafter/gptq_lm_head.py models/Qwen3.8-27B-W4A16-AutoRound models/tmp-lm4 --bits 4 --calib-rows 300000
$V prepare/build_draft_vocab.py models/tmp-lm4 --ids prepare/draft_vocab_ids.json
$V drafter/requant_mtp_gptq.py models/tmp-lm4 models/Qwen3.8-27B-W4A16-AutoRound-fast drafter/runs/e/mtp_hessians.pt --bits 4
```

可选微调仅作记录：`train_mtp.py --out runs/r --depths 2 --depth-weights 1,0.5 --epochs 1 --lr 3e-5 --micro-tokens 4096`，然后执行 `export_mtp.py`。训练器通过重放带 KV history 的 drafter 调用，将自身结果复现到 vLLM 的 1% 以内；应先使用 `--eval-only`，只统计 response token 和真实 token criterion。

## DFlash2 drafter：W4A16 重量化
`SPEC=dflash2` 单用户模式使用 [incoai/Qwen3.8-27B-DFlash2](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2)，包含 5 个 Qwen3 风格层、hidden 5120、8 个 KV head×128、MLP 17408、将目标第 5／19／33／47／61 层 hidden state 投影到 drafter 的 `fc`、动态卷积和 candidate selector；1.92B 参数，bf16 为 3.85 GB。每个 decode step 读取一次，3090 上约 5 ms，21K-token KV pool；因此使用 compressed-tensors W4A16（Marlin）重写为 1.19 GB：`syvai/Qwen3.8-27B-DFlash2-W4A16`。

重建命令：
```bash
V=venv/bin/python
$V prepare/fetch_dflash2.py --bf16
DRAFT=models/Qwen3.8-27B-DFlash2 $V drafter/capture_dflash2.py --prompts 400 --max-tokens 384
$V drafter/quant_dflash2.py models/Qwen3.8-27B-DFlash2 models/Qwen3.8-27B-DFlash2-W4A16 drafter/runs/dflash2/hessians.pt
```

## 测量结论
- int4 GPTQ 保持 greedy acceptance（3.34–3.65，对比 bf16 的 3.54 tokens/step），默认采样损失约 5%（3.2 对 3.4）。int4 噪声影响 acceptance probability，不影响 argmax；每 step 少读 2.7 GB，配合 fast variant 后将 DFlash2 从无收益变为有收益。
- `fc` 保持 bf16 而不是 int4（增加 0.26 GB）没有 acceptance 差异：3.17 对 3.17。
- 将 context-KV 输入分布混入 k/v Hessian 会使 greedy acceptance 下降 7%，3.34→3.12 tokens/step，126→118 tok/s；因此发布的 drafter 不使用该校准。
- 对 selector walk 的 16-candidate proposal 应用请求的 top-k/top-p，缓存截断但 verify 仍无损，收益约 2%，在噪声范围内，默认关闭（`VLLM_DFLASH2_DRAFT_TOPK_TOPP=0`）。
- int4 矩阵相对权重误差均值为 0.147（Frobenius），与 MTP 模块相近。

## 费时事项
- `capture.py` 按 vLLM request id 对齐 hidden state；0.27 中 request id 形如 `counter-uuid`，并按单步内 `input_batch.req_ids` 顺序处理。
- decode 阶段 hidden state 与 prefill 阶段相差约 0.9%；在任一阶段训练都会得到相同 drafter。
- rejection 后紧邻的位置系统性更难；其逐位置 acceptance 比整段 top-1 率低约 5 个百分点，`train_mtp.py --eval-only` 的链模拟会处理这一点。
- 带 speculation 的 greedy decode 在不同 drafter 配置间不是 bit-deterministic；8 个 prompt×1K token 的 tokens/step 可有 ±3% 波动，DFlash2 的启动形制间范围更宽，因此 2% 差异必须重复验证。
- `capture_dflash2.py` 中，进程内 vLLM 引擎在 `del llm` 后不会归还 GPU 内存，Hessian reduction 需要重新执行进程；融合 `qkv_proj.weight_shape` 只保存最后分片形状，应从 `weight_packed`／`input_size` 推导 dense shape。

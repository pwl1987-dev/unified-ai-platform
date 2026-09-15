# B2-B 引擎相位两种 env 形制（§8.4/§8.6）

两形制均派生自 `.env.prod-130-certified.bak-20260908`（生产认证内容），单变量 DRAFT
+ 如下记忆预算差异；其余（MODEL/SPEC/DFLASH_TOKENS=7/LOOKUP=0/GPU_UTIL/CUDAGRAPH/
EXTRA_ARGS 等）逐项相同。

| 项 | certified（生产形制） | lean（b0 形制） |
|---|---|---|
| MAX_LEN / DFLASH_MAX_LEN | 245760 | 32768 |
| KV_MEM | 4860000000 | 2000000000 |
| boot 行为 | 确定性（Q 两次 boot FINAL-60 60/60 逐位一致） | boot 间布局混沌（相位均值 ±0.1–0.2） |
| 可 boot drafter | int4（W/Q/S3）；bf16 drafter（C0/S1）OOM | 全部 |

lean 存在的原因：bf16 drafter 3.6GB + 固定 KV 4.86GB 在 23.5GB 单卡装不下
（B1-C/B2-A 同一先例：b2a REPORT「b0 配置实测可跑」）。

五相位 env 实件归档在 `envs/`：`env-*.env` = certified 形制（certified 对照 W/Q 用），
`env2-*.env` = lean 形制（五相位主跑用；文件内为「基线块+certified 块+lean 追加块」，
后者覆盖前者）；生产基线原件见 `../../p0/arms/prod.env.bak`（DRAFT=recal）。

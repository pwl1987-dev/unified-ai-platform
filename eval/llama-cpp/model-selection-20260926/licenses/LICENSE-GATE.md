# License Gate（四仓 exact revision，2026-09-26 抓取）

## ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF @ d562806

- **Apache-2.0**（front-matter 明示；权重继承 Qwen/Qwen3.8-27B 的 Apache-2.0）。
- 商用：允许，无收入门槛。再分发：Apache-2.0 条款（附许可证副本 + NOTICE）。
- mmproj 同仓同许可。
- 结论：`PRODUCTION-LEGAL-ELIGIBLE`（Apache-2.0 常规义务）。

## ukisai/Swift-*（三仓，Swift 1.0 / 1.5 / 1.5-GSQ，license: other = Swift Open License v1.0）

全文见 `swift-open-license-1.0.txt`（自 GSQ 仓 LICENSE 逐字存档；normal/1.0 仓 LICENSE 落地后复核）。

- Licensor：UkisAI；Work = Swift Contribution + Qwen3.8-27B（Base Model, Apache-2.0, Alibaba Cloud 2026）的 Derivative Work。
- **商用收入门槛（§5）**：法人实体最近财年总收入 ≥ **US$1,000,000**（含受控实体合并）时，
  商用**不在本许可授权范围内**，需另签 Swift Enterprise License（ukisai.com/contact）。
  §501(c)(3) 类非营利的研究/非商业用途豁免门槛。
- 再分发：须附带本许可副本 + 修改声明 + 保留版权/商标/归属声明 + NOTICE 内容；
  含 Base Model 部分（含量化后的权重）还须附带 Apache-2.0 并遵守之。
- 商标：不得使用 "Ukisai"、"Swift" 商标名（合理描述来源除外）。
- 终止：违反条款立即终止，须停止使用并删除 Swift Contribution 副本（Base Model 权利不受影响）。
- **结论：`LICENSE_REVIEW_REQUIRED`** —— 使用方年收入是否 < US$1M 决定能否商用；
  本报告不给法律意见，交由业务方确认。技术 Winner 若为 Swift 系，
  标记 `TECHNICAL_WINNER_BUT_LICENSE_REVIEW_REQUIRED`。

## 对选型的影响

- 若业务方收入 ≥ $1M 且不打算签企业协议 → PRIMARY 只能落在 ISTA(Apache-2.0) 或其他 Apache 系模型。
- Swift 系即便技术全面领先，也必须先过商业条款确认这一关。

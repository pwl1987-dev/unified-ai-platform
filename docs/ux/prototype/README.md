# Unified AI Platform Hi-fi Prototype

这是 WP-P2-07 的**静态视觉验证原型**。

## 打开方式

直接在浏览器打开：

- index.html

不需要 npm、Vite、React、服务端或网络依赖。

## 覆盖

- Home / Needs Your Attention
- AI Hub + Model Detail
- Deployment Promotion + LKG
- Experiment / Benchmark
- Compute / GPU
- Governance
- Approval Inbox
- AI Operator
- Light / Dark

## 重要边界

这不是正式前端实现。

禁止把本目录当作：

- Domain/API Authority；
- mock backend；
- 产品运行时代码；
- 第三方 Backend 管理入口。

正式 React 实现必须继续依赖：

- contracts/openapi/
- contracts/schemas/
- contracts/events/
- contracts/state-machines/
- contracts/adapters/
- contracts/ui/design-tokens.v1.json

并通过 generated client 和 Contract CI。

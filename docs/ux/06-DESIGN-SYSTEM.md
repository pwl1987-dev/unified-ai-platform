# Design System Direction v1.0

> Work Package：**WP-P2-06 Design System Direction**
>
> 状态：**Baseline Frozen for Hi-fi / React Shell**
>
> Machine-readable baseline：contracts/ui/design-tokens.v1.json
>
> 输入：Roles、Human-AI Responsibility、Golden Journeys、Information Architecture、Low-fi Wireframes、Northbound API / State / Adapter Contract。
>
> 本 WP 冻结视觉语义、组件行为和信息密度；**不是最终品牌视觉成品稿**。P2-07 才进入 Hi-fi Visual Prototype。

# 1. 产品视觉定位

Unified AI Platform 的视觉方向冻结为：

> **专业控制平面 + 工程工作台 + Evidence-first 决策界面。**

它不是 consumer chat app、GPU 大屏、vendor backend admin console，也不是卡片堆叠式 BI dashboard。

目标：

- 稳定、克制、专业；
- 高信息密度但不拥挤；
- Authority / Risk / Status 清楚；
- 长任务、复杂对象和 Evidence 可持续阅读；
- AI 明确存在，但不抢夺 Domain Authority。

# 2. App Shell

Desktop 第一阶段采用：

~~~text
┌──────────────────────────────────────────────────────────────────────┐
│ Top Utility Bar                                                      │
│ Project | Environment | Search | Attention | AI Operator | Notify    │
├───────────────┬──────────────────────────────────────────────────────┤
│ Primary Nav   │ Main Workspace                                       │
│ Home          │                                                      │
│ AI Hub        │                                      Context Rail    │
│ Build         │                                      optional        │
│ Run           │                                                      │
│ Improve       │                                                      │
│ Knowledge     │                                                      │
│ Compute       │                                                      │
│ Govern        │                                                      │
└───────────────┴──────────────────────────────────────────────────────┘
~~~

冻结理由：

- 8 个一级导航用左侧 Rail 比横向菜单更稳定；
- Top Bar 专门承载 Scope / Environment / Search / Attention / Operator；
- Main Workspace 给表格、Diff、Evidence、Metric 足够横向空间；
- Context Rail 承载 Gate / Approval / Evidence，不打断主任务。

## 2.1 Primary Nav

- expanded：240px；
- collapsed：64px；
- icon + text；
- active state；
- keyboard complete；
- collapsed 时有 tooltip；
- badge 只用于真正需要处理的 count。

## 2.2 Top Utility Bar

顺序：

1. Project Scope；
2. Environment；
3. Global Search；
4. Needs Your Attention；
5. AI Operator；
6. Notifications；
7. User / Acting as。

Production 必须始终显示文本，不只靠颜色。

## 2.3 Context Rail

- 320–400px；
- 可折叠；
- 决策型 Detail 默认展开；
- 大表格页默认可折叠。

固定顺序：

1. State / Health；
2. Evidence；
3. Gate；
4. Approval；
5. External implementation；
6. Audit。

# 3. Layout / Grid

- desktop page padding：24px；
- section gap：24px；
- content gap：16px；
- inline control gap：8px；
- Detail 使用 12-column logical grid；
- Context Rail 存在时主区最小约 720px；
- <1280px：Rail 可 overlay；
- <1024px：Primary Nav 默认 collapsed；
- 第一阶段不是 mobile-first，但 Approval / Attention 在 tablet 宽度必须可用。

# 4. Spacing

统一 scale：

~~~text
4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
~~~

禁止局部随意出现 5/7/13/19px 等不受控 spacing。

# 5. Typography

## 5.1 Font Strategy

Latin / number：

~~~text
Inter → system-ui
~~~

Chinese：

~~~text
Noto Sans SC → PingFang SC → Microsoft YaHei → system sans
~~~

要求：

- 不强依赖第三方 CDN；
- font failure 不破坏 layout；
- Domain ID / hash / code 使用 system monospace；
- implementation 可 self-host。

## 5.2 Type Scale

| Role | Size / Line | Weight |
|---|---:|---:|
| Page title | 24 / 32 | 600 |
| Section title | 18 / 28 | 600 |
| Subsection | 16 / 24 | 600 |
| Body | 14 / 22 | 400 |
| Body strong | 14 / 22 | 600 |
| Table / metadata | 13 / 20 | 400 |
| Caption | 12 / 18 | 400 |

控制平面不使用营销式超大标题。

## 5.3 Numbers

GPU、latency、token、cost、power、percentage：

- tabular numbers；
- 单位明确；
- 精度按业务固定；
- Unknown 显示 — / Unknown，不能伪装成 0。

# 6. Color / Semantic Tokens

颜色按：

~~~text
Primitive palette
→ Semantic token
→ Component state
~~~

业务页面禁止直接依赖颜色值或 vendor class；使用 semantic token。

基础语义：

- canvas；
- surface；
- surface-elevated；
- surface-muted；
- border / border-strong；
- text-primary / secondary / muted；
- action-primary；
- focus-ring。

状态语义：

- success；
- info；
- warning；
- danger；
- neutral；
- lkg；
- production；
- environment-production。

具体 light/dark baseline 位于 contracts/ui/design-tokens.v1.json。

# 7. Lifecycle / Gate / Approval Color Mapping

| Domain state | Semantic |
|---|---|
| Candidate | info |
| Production | production/success |
| Failed | danger |
| Degraded | warning |
| Blocked | warning / danger by severity |
| LKG designation | lkg |
| Pending | neutral |
| Running | info |
| Retired / Archived | neutral |

Production 与 LKG 可以同时成立，因此必须允许：

~~~text
[PRODUCTION] [LKG]
~~~

而不是互斥单色状态。

Gate：

- PASS = success；
- FAIL = danger；
- BLOCKED = warning；
- NOT_EVALUATED = neutral。

Approval：

- REQUESTED / PENDING = warning；
- APPROVED = success；
- REJECTED = danger；
- EXPIRED = neutral；
- REVOKED = danger；
- CHANGES_REQUESTED = info/warning。

# 8. Responsibility R0-R3

责任等级不是风险色阶，必须 icon + 文本 + token：

- R0：Neutral — AI/System may execute within policy；
- R1：Info — AI may propose only；
- R2：Warning — Human approval required；
- R3：Human-only — 强文本/图标，不允许被 AI recommendation 混淆。

所有 dangerous action 必须显示当前 R-level。

# 9. Environment Visual Contract

Sandbox / Development / Staging / Production 使用独立 EnvironmentBadge。

Production：

- Top Bar 持续显示 PRODUCTION；
- dangerous dialog 重复环境；
- 不用全页红底；
- 不与 Error 完全共享一套视觉；
- mutation 必须再次显示 scope/environment。

目标是明确，而不是制造 warning fatigue。

# 10. Density

两档：

## Comfortable-Dense — Default

- table row：40px；
- controls：36–40px；
- toolbar：40px；
- card padding：16px。

## Compact

- table row：约 34px；
- toolbar：约 34px；
- card padding：12px。

Compact 仅用于 GPU inventory、event/log table、dependency matrix、large benchmark result。

关键 action target 不得过小。

# 11. Tables

Table 是核心组件，不退化为 Card list。

必须支持：

- sticky header；
- column visibility；
- resize；
- sort/filter；
- cursor pagination；
- row selection；
- keyboard navigation；
- stable ID copy；
- observed_at / stale；
- empty/loading/error/partial states。

常见列顺序：

~~~text
Name
Status
Key business field
Environment / Scope
Owner
Observed / Updated
Evidence / Attention
Actions
~~~

ExternalRef/vendor detail 默认不占主列。

高风险 bulk mutation 默认禁用；Approval Inbox 不允许盲目批量批准不同 scope 的请求。

# 12. Forms

Form 按：

~~~text
Intent / Spec
Validation
Impact
Evidence / Policy
Action
~~~

规则：

- Spec 与 Status 视觉分区；
- business revision 明确；
- resource_version 不作为普通可编辑字段；
- secret 通过 SecretRef picker，不进入普通 plaintext field；
- field validation、server Policy、Gate/Approval error 分开表达。

# 13. Buttons / Actions

层级：

- Primary；
- Secondary；
- Ghost；
- Danger；
- AI Suggestion。

动作使用清楚动词：

- Run evaluation；
- Generate proposal；
- Request approval；
- Promote；
- Recover to LKG。

避免高风险场景只写 OK / Submit / Execute。

AI Suggestion 使用独立 AI icon + 文本，不能伪装为已经执行的 Primary action。

# 14. Dangerous Action Pattern

Dialog/Drawer 必须显示：

- Action；
- Acting as；
- Project；
- Environment；
- Responsibility；
- Affected Objects；
- Side Effects；
- Gate；
- Approval；
- Evidence destination；
- Rollback/LKG；
- current resource_version。

R2 显示 Request Approval，不把 Promote 做成一个误导性的“看似可点但灰掉”按钮。

R3 Approval 必须 Human actor + reason。

# 15. Cards

Card 只用于：

- Attention；
- summary；
- Decision Packet；
- Evidence summary；
- small entity preview。

不用 Card 替代：

- large table；
- dense settings；
- long Evidence history；
- comparison matrix。

避免“一项 KPI 一张巨大卡片”。

# 16. Status Component

统一 StatusBadge + StatusSummary。

StatusBadge：

- icon；
- text；
- semantic；
- optional reason。

StatusSummary：

- phase；
- health；
- observed_at；
- reason；
- stale；
- source。

Backend unavailable 必须支持：

~~~text
Domain state: READY
Backend observation: UNAVAILABLE
~~~

不能把整个对象伪装成 NOT_FOUND。

# 17. Alert / Needs Your Attention

Alert 分类：

- info；
- warning；
- blocking；
- security；
- recovery。

Attention item 必须回答：

- 为什么需要我；
- 到期时间；
- 谁能处理；
- Evidence；
- safe primary action。

普通“任务完成”只进入 Notifications，不进入 Attention。

# 18. Evidence

Evidence 是核心视觉语义。

第一批组件：

- EvidenceRef；
- EvidenceList；
- EvidenceTimeline；
- EvidenceSummary。

展示：

- type；
- summary；
- immutable hash；
- producer；
- produced_at；
- raw/artifact link；
- superseded/invalid marker。

Failed Evidence 不隐藏。

Promotion / Approval / Gate 的 Evidence 必须在 primary decision flow 可见。

# 19. Gate

GatePanel 展示：

- Gate name；
- definition revision；
- subject revision；
- PASS / FAIL / BLOCKED；
- checks；
- Evidence；
- evaluated_at。

禁止 editable PASS / force-pass / ignore-and-continue。

治理例外进入 Approval/Policy exception，不改 GateResult。

# 20. Approval

DecisionPacket 是 Approval Inbox 的核心组件：

~~~text
Action
Affected object
Requester / Acting as
Scope / Environment
Responsibility
Gate
Evidence
Side effects
Rollback / LKG
AI recommendation (Advisory)
Human reason
Approve / Reject
~~~

AI recommendation 视觉权重必须低于人类决策区。

# 21. AI Operator

支持两种形态：

- Docked panel：explain / summarize / propose / cross-page context；
- Full workspace：multi-step plan / long workflow / Decision Packet / incident recovery。

每一步必须有状态：

- Suggested；
- Proposed；
- Executed；
- Waiting Approval；
- Rejected；
- Failed；
- Rolled Back。

Executed 必须带 timestamp + actor + request/operation/evidence ref。

AI 文本不能使用“系统已执行”视觉样式，除非有真实 execution record。

# 22. Graph / Visualization

只使用能支持决策的图：

- time series；
- distribution；
- Pareto/scatter；
- comparison；
- capacity；
- topology；
- lineage DAG；
- rollout progression。

禁止 decorative donut、3D chart、无单位 sparkline、不可追溯 summary score。

图必须有：

- 单位；
- time range；
- source/observed_at；
- accessible table fallback；
- keyboard tooltip；
- 非颜色唯一语义。

# 23. Experiment / Benchmark

默认采用：

- comparison table；
- Pareto；
- metric drill-down；
- raw Evidence。

至少能展示：

- Quality；
- Latency；
- Throughput；
- VRAM；
- Power；
- Cost；
- Reliability。

任何 Gate check 失败必须直接可见。

# 24. Compute

GPU/Node 以 Table + topology/detail 为主。

每个 GPU 显示：

- stable ID；
- Node；
- health；
- VRAM；
- utilization；
- power/temp；
- allocation；
- workload；
- observed_at。

不以 8 个巨大 GPU 卡片作为主视图。

# 25. Empty / Loading / Error

Empty：解释是什么、为什么空、下一安全动作。

Loading：

- skeleton 保持 layout；
- mutation 不重复提交；
- long-running 使用 Operation state，而不是无限 spinner。

Error 明确区分：

- Control Hub error；
- Permission denied；
- Backend unavailable；
- Partial failure；
- stale observation。

禁止统一 Something went wrong。

# 26. Dark Mode

Dark Mode 是 first-class，不做 CSS invert。

要求：

- Surface 层级清楚；
- Status semantic 单独调校；
- chart grid 克制；
- ID/hash 可读；
- focus ring 足够；
- screenshot/投屏仍可区分；
- status 不只靠颜色。

默认跟随系统，用户可手工切换。

# 27. Accessibility

目标：**WCAG 2.2 AA baseline**。

必须：

- keyboard complete；
- visible focus；
- skip navigation；
- heading hierarchy；
- accessible name；
- status text；
- form error association；
- dialog focus trap；
- reduced motion；
- contrast；
- graph table fallback；
- icon tooltip + accessible name；
- no color-only meaning。

Approval / Dangerous Action 优先做 screen-reader flow audit。

# 28. Motion

- UI transition 120–200ms；
- respects prefers-reduced-motion；
- 不用循环“AI 思考动画”代替真实 Operation state；
- long-running 显示 operation phase + last update。

# 29. Iconography

使用统一 line icon family。

需要语义 icon：

- AI；
- Evidence；
- Gate；
- Approval；
- Warning；
- External implementation；
- LKG；
- Production；
- Scope；
- Environment。

Icon 不单独承担关键语义。

# 30. Language / i18n

UI 从第一天使用 i18n key。

第一优先：

- zh-CN；
- en-US 预留。

Domain stable ID、API field、hash 不翻译。

禁止用中文展示字符串参与业务逻辑判断。

# 31. Component Foundation

已冻结技术：

- React；
- TypeScript；
- shadcn/ui + Base UI。

使用方式：

- shadcn 提供可拥有源码的基础组件；
- Base UI 提供 accessible primitive；
- 我们拥有 semantic component layer；
- shadcn class name 不能成为 Product Contract。

第一批 semantic components：

~~~text
AppShell
ScopeSwitcher
EnvironmentBadge
StatusBadge
ResponsibilityBadge
EvidenceList
GatePanel
DecisionPacket
ApprovalActions
AttentionItem
DomainHeader
SpecStatusSplit
OperationProgress
ExternalImplementationPanel
DataTable
MetricComparison
AIActionStep
DangerActionDialog
~~~

# 32. Token Ownership

contracts/ui/design-tokens.v1.json 是 semantic token baseline。

未来映射到：

- CSS variables；
- Tailwind/shadcn tokens；
- chart theme；
- component variants。

业务页面不能直接依赖 primitive hex。

# 33. P2-07 Hi-fi 输入

第一轮 Hi-fi 至少完成：

1. Home + Needs Your Attention；
2. AI Hub + Model Detail；
3. Deployment Candidate → Approval → Production；
4. Experiment / Benchmark；
5. Compute / GPU；
6. Governance / Approval Inbox；
7. AI Operator；
8. Light + Dark representative screens。

Hi-fi 不重新打开：

- IA；
- Domain；
- State Machine；
- R0-R3；
- Approval/Gate；
- Adapter boundary。

如果视觉稿需要新对象/API，登记 Contract Gap，不能在前端私建。

# 34. Acceptance Criteria

- [x] Color semantic tokens；
- [x] Typography；
- [x] Spacing；
- [x] Density；
- [x] App Shell；
- [x] Table / Form / Card；
- [x] Status / Environment / R0-R3；
- [x] Evidence / Gate / Approval；
- [x] AI suggestion / execution；
- [x] Graph；
- [x] Dark Mode；
- [x] WCAG 2.2 AA；
- [x] zh-CN first-class / i18n；
- [x] machine-readable design tokens；
- [x] 未开始业务前端编码。

# 35. Exit Condition

WP-P2-06 完成。

下一 UX Work Package：

**WP-P2-07 Hi-fi Visual Prototype**

P3-01 Repository Skeleton 已由 P1 Contract Closure 判定 GO，可由编码线并行；P2-07 不阻塞纯目录/Contract CI skeleton，但真实 Product UI implementation 应等待 Hi-fi 第一轮稳定。

# Hi-fi Visual Prototype v1.0

> Work Package：**WP-P2-07 Hi-fi Visual Prototype**
>
> 状态：**Visual Baseline Complete**
>
> 静态原型入口：docs/ux/prototype/index.html
>
> 约束：该原型只用于视觉、信息层级、状态语义与任务路径验证；**不是产品前端代码，不进入 apps/web，不拥有 Domain/API Authority。**

# 1. 目标

P2-07 把此前已经冻结的：

- Roles；
- R0/R1/R2/R3；
- Golden Journeys；
- Information Architecture；
- Low-fi；
- Design System Direction；
- P1 Contract Closure；

转成第一套可直接浏览的高保真视觉基线。

不重新打开：

- Domain Model；
- Northbound API；
- Event；
- State Machine；
- Adapter boundary；
- Approval/Gate Authority；
- 一级导航。

# 2. 原型形态

采用零依赖静态 HTML/CSS/JS：

~~~text
docs/ux/prototype/
├── index.html
├── styles.css
└── app.js
~~~

原因：

1. 可直接在浏览器打开；
2. 不需要 Vite/React 构建；
3. 不进入正式产品代码；
4. 不依赖外部 CDN；
5. 可作为 P3/P8 前端实现的视觉验收参考；
6. Git diff 可读。

# 3. 第一轮覆盖页面

原型包含 8 个代表性场景：

1. **Home + Needs Your Attention**
2. **AI Hub + Model Detail**
3. **Deployment Candidate → Approval → Production**
4. **Experiment / Benchmark**
5. **Compute / GPU**
6. **Govern**
7. **Approval Inbox**
8. **AI Operator**

并包含：

- Light Mode；
- Dark Mode；
- Production Environment 持续标识；
- Project Scope；
- Acting as；
- Status / Evidence / Gate / Approval；
- Candidate / Production / LKG；
- R0 / R1 / R2 / R3；
- External implementation ≠ Authority；
- Backend unavailable / partial failure 视觉语义。

# 4. 关键视觉裁决

## 4.1 控制平面，不做“炫技大屏”

Home 使用：

- Attention first；
- compact KPI；
- active operations table；
- production health；

而不是全屏图表和巨大数字卡。

## 4.2 Capability-first

AI Hub 默认主体是 Capability，不是模型品牌。

Model Detail 作为右侧 Detail Pane，展示：

- ModelAsset stable ID；
- business revision；
- source/license；
- capability mapping；
- evaluation；
- candidate / production / LKG；
- ExternalRef。

## 4.3 Promotion 决策路径

Deployment 页面显式拆开：

~~~text
Candidate
Production
LKG
Gate
Approval
Rollout
~~~

Gate PASS 不等于可直接上线。

R2 action 首先显示 Request Approval。

## 4.4 Approval Inbox

AI recommendation 降低视觉权重并标记 Advisory。

Human decision：

- Approve；
- Reject；
- Reason required；

是唯一最终决策区。

## 4.5 AI Operator

Operator 不表现成“万能聊天框”。

它展示：

- Acting as；
- Project；
- Environment；
- Responsibility；
- Plan；
- step state；
- proposed action；
- Evidence；
- Gate；
- Approval；
- LKG。

Suggestion 与 Executed step 使用不同视觉和时间戳。

# 5. Design Token 对齐

原型颜色与布局语义来自：

- contracts/ui/design-tokens.v1.json

原型代码虽然为了零依赖直接定义 CSS variable，但变量名保持 semantic：

- canvas；
- surface；
- text-primary；
- success；
- warning；
- danger；
- info；
- lkg；
- production；
- focus ring。

正式 React 实现必须从 machine-readable token baseline 生成/映射，不复制 prototype CSS 作为产品 Authority。

# 6. Accessibility

原型第一轮已经按 Design System Direction 保持：

- button 使用可访问名称；
- theme toggle 可键盘操作；
- nav button 有 active state；
- 状态有文字，不只用颜色；
- table 保留文本；
- Production 有持续文本；
- AI execution 有明确状态文本；
- reduced-motion CSS；
- focus-visible；
- Dark Mode 独立 token。

P8 实现仍需要自动化 accessibility test，不以静态原型替代。

# 7. Contract Traceability

| Prototype surface | Contract |
|---|---|
| Capability catalog | /api/v1/capabilities |
| Model Detail | ModelAsset read model |
| Deployment detail | GET /api/v1/deployments/{deployment_id} |
| Promotion | :promote + Gate/Approval |
| Recover to LKG | :recover |
| Experiment | Experiment + Run/Evidence |
| GPU table | /api/v1/resources/gpus |
| Approval Inbox | Approval DecisionPacket |
| AI Operator | common Northbound API + ExecutionContext |
| External implementation | Adapter / ExternalRef only |

原型没有 invented endpoint。

# 8. Product Implementation Guard

P3/P8 前端实现：

- 可以复制信息架构和组件语义；
- 可以复用 design token；
- 可以复用静态原型内容结构；

但不能：

- 把 prototype mock data 变成 hard-coded product truth；
- 绕过 generated client；
- 把 ExternalRef 当 route ID；
- 直接接第三方 Backend；
- 让 AI Operator 调 backend admin API；
- 自行 PATCH status。

# 9. Acceptance Criteria

- [x] Home + Attention 有 Hi-fi baseline。
- [x] AI Hub + Model Detail 有 Hi-fi baseline。
- [x] Deployment Promotion / LKG 有 Hi-fi baseline。
- [x] Experiment/Benchmark 有 Hi-fi baseline。
- [x] Compute/GPU 有 Hi-fi baseline。
- [x] Govern 有 Hi-fi baseline。
- [x] Approval Inbox 有 Hi-fi baseline。
- [x] AI Operator 有 Hi-fi baseline。
- [x] Light / Dark representative view。
- [x] Production / Candidate / Failed / LKG 可区分。
- [x] spec / status 可区分。
- [x] Evidence / Gate / Approval 可见。
- [x] AI suggestion ≠ executed action。
- [x] External Backend detail 不成为 Authority。
- [x] 静态原型不进入产品代码路径。
- [x] 未引入新 Contract Gap。

# 10. P2 Exit

P2 UX 主线第一轮已完整闭环：

~~~text
P2-01 Roles
→ P2-02 Human-AI Responsibility
→ P2-03 Golden Journeys
→ P2-04 IA
→ P2-05 Low-fi
→ P2-06 Design System
→ P2-07 Hi-fi Visual Prototype
~~~

**P2 First-pass = COMPLETE。**

下一阶段可以：

- P3-01 Repository Skeleton；
- P3-05 Contract CI 优先；
- React 只先做 App Shell + generated API client + semantic component foundation；
- 复杂业务页面仍按 Golden Journey 分批实现。

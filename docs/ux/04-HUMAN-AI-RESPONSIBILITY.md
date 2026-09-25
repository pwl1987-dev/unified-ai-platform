# Human-AI Responsibility Matrix v0.1

> Work Package: **WP-P2-02 — Human-AI Responsibility Matrix**  
> Status: **FIRST RESPONSIBILITY BASELINE — FROZEN FOR GOLDEN JOURNEYS / IA / LOW-FI**  
> Date: **2026-09-25**  
> Inputs: `docs/ux/01-ROLES.md`, `docs/design/10-DOMAIN-MODEL.md`  
> Principle: **Agents drive workflow; platform controls authority.**

---

# 1. 目的

本文件回答：

> 在平台中，哪些动作 AI 可以直接执行，哪些只能建议，哪些必须经过人类批准，哪些最终决定只能由人做？

目标不是压低自动化，而是让自动化可以长期安全运行。

平台希望做到：

```text
尽可能自动
+
关键责任不失控
+
所有高风险动作有证据
+
审批不是形式按钮
+
AI 不通过换入口获得更高 Authority
```

---

# 2. 四级责任定义

所有受控动作必须落入以下四类之一。

## R0 — AI_CAN_EXECUTE

AI 可以在当前用户/服务的有效权限和 Policy 内直接执行。

必须满足：

- 已有明确授权；
- 在允许环境；
- 在 budget 内；
- 副作用可接受；
- 不跨安全/数据/License 边界；
- 有完整 audit/evidence；
- 失败有恢复路径。

典型：

- read/search；
- health probe；
- benchmark；
- non-production experiment；
- index rebuild；
- 自动扩缩容（预授权 Policy 内）。

---

## R1 — AI_CAN_PROPOSE_ONLY

AI 可以：

- 分析；
- 生成 plan；
- 生成 diff；
- 给出 recommendation；
- 准备 command/change set；
- 收集 Evidence。

但不能直接触发真实 mutation。

适合：

- Policy change proposal；
- backend replacement design；
- dependency risk recommendation；
- production architecture change；
- unclear-risk operation。

R1 的价值是：

> AI 把决策材料准备完整，但不自行越过责任边界。

---

## R2 — HUMAN_APPROVAL_REQUIRED

AI 可以准备并在批准后执行，但 **不可在批准前生效**。

流程：

```text
AI/User proposes
      ↓
Decision Packet
      ↓
Human Approval
      ↓
Policy re-check
      ↓
AI/System executes
      ↓
Evidence
      ↓
Post-condition verification
```

典型：

- Production Promotion；
- Permission grant；
- sensitive Data Export；
- production quota change；
- backend cutover；
- destructive delete。

---

## R3 — HUMAN_ONLY

AI 可以准备材料，但某个关键最终行为本身必须由人完成。

主要是：

- 最终法律/治理责任决定；
- 最终 security exception decision；
- 最终 license override decision；
- 最终 Approval decision；
- 某些不可代理的身份确认。

R3 不代表“所有操作都由人手工敲命令”。

例如：

```text
License Override
AI prepares evidence     = allowed
Human decides override   = HUMAN_ONLY
System applies decision  = automated after decision
```

---

# 3. Authority 计算公式

责任等级不是只看动作名。

有效决定必须基于：

```text
Action
+ Actor Role
+ Resource Scope
+ Environment
+ Data Classification
+ Risk Level
+ Reversibility
+ Budget
+ Policy
+ Evidence
+ Separation of Duty
= Effective Responsibility Level
```

因此：

> “AI can execute” 永远不是平台级永久白名单。

同一个动作可能：

```text
dev     → R0
staging → R0/R2
prod    → R2
regulated / exceptional → R3 decision
```

---

# 4. 环境分级

第一轮 UX 使用四级环境语义：

| Environment Class | 含义 |
|---|---|
| Sandbox | 实验隔离环境，不承载真实业务责任 |
| Development | 开发集成环境 |
| Staging | 接近生产、用于验证与演练 |
| Production | 正式业务能力 |

额外横向标签：

```text
Sensitive Data
Restricted License
Security Critical
High Cost
Irreversible
Public / External
```

任何横向标签都可以提升 Responsibility Level。

---

# 5. 默认责任矩阵

## 5.1 Model / Capability / Deployment

| Action | Sandbox / Dev | Staging | Production / External | Default Human Role | Notes |
|---|---|---|---|---|---|
| Discover model | R0 | R0 | R0 | AI Engineer | 只读发现 |
| Import model candidate | R0 | R0 | R1/R2 if restricted | AI Engineer | 必须先做 source/license evidence |
| Capability probe | R0 | R0 | R0 | AI Engineer | 无 destructive side effect |
| Benchmark | R0 | R0 | R0 within budget | AI Engineer | 高成本时升级 R2 |
| Create candidate deployment | R0 | R0 | R0 candidate only | AI Engineer | 不等于 Production |
| Start/stop non-prod deployment | R0 | R0 | — | AI Engineer / SRE | 按 quota |
| Production Promotion | — | R1 | **R2** | Approver | AI 可执行已批准 rollout |
| Production rollback to approved LKG | — | R0/R2 by policy | **R0 if pre-authorized incident policy; otherwise R2** | SRE | rollback policy 必须提前冻结 |
| Change quality Gate threshold | R1 | R1 | **R2/R3 governance decision** | Gate owner / Approver | AI 不可为通过而降低 Gate |
| Public/external Model Publish | R1 | R1 | **R2** | Approver / owner | License/Data/Security 先过 Gate |
| Deprecate Capability | R1 | R1 | **R2** if production consumers | Capability owner | 需要 impact evidence |
| Retire Deployment | R0 | R0/R2 | **R2** | SRE / owner | 确认无 active traffic |

---

## 5.2 Data / Knowledge

| Action | Low-risk internal | Sensitive / Restricted | External / Public | Human Role | Notes |
|---|---|---|---|---|---|
| Import dataset | R0 | R0 into quarantine | R0 into quarantine | Data Engineer | 导入不代表可使用 |
| Profile / dedupe | R0 | R0 | R0 | Data Engineer | 结果写 Evidence |
| Auto-label proposal | R0 | R0 | R0 | Data Engineer | 接受标签按质量 Policy |
| Change classification | R1 | **R2** | **R2** | Data owner/Security | 降级 classification 风险更高 |
| Build/rebuild index | R0 | R0 | R0 | Data Engineer | Index 为 derived |
| Delete/rebuild derived index | R0 | R0 | R0 | Data Engineer | canonical source 不受影响 |
| Export non-sensitive internal data | R0 | — | — | Data Engineer | 必须有 scope |
| Sensitive Data Export | — | **R2** | **R2/R3 if policy demands** | Data owner/Security | approval packet 要有目的/范围/expiry |
| External Provider data transfer | R1 | **R2** | **R2** | Security/Data owner | privacy policy mandatory |
| Delete canonical Dataset/Knowledge | **R2** | **R2** | **R2** | Owner/Approver | destructive delete flow |
| Remove source/license attribution | **禁止** | **禁止** | **禁止** | — | 不通过 R0-R3 放行 |

---

## 5.3 Compute / SRE

| Action | Non-prod | Production | Emergency | Human Role | Notes |
|---|---|---|---|---|---|
| Inventory / health probe | R0 | R0 | R0 | SRE | read/observe |
| Autoscale within frozen policy | R0 | R0 | R0 | SRE | budget/SLA policy 限制 |
| Scheduler placement | R0 | R0 | R0 | Platform | normal automation |
| Drain non-prod node | R0 | — | — | SRE | |
| Drain production node | — | R0 if maintenance policy / R2 otherwise | R0 if incident policy | SRE | 需 workload evacuation evidence |
| Restart workload | R0 | R0 if bounded recovery policy | R0 if bounded recovery policy | SRE | retry limit / backoff |
| Reboot VM/Node | R0 | R2 unless pre-authorized | R0/R2 by incident policy | SRE | blast radius |
| Modify GPU scheduling policy | R1 | **R2** | R2 | Platform Admin/SRE owner | 不逐次审批 placement |
| Increase global compute budget | R1 | **R2** | R2 | Approver | |
| Cloud burst / external compute | R1 | **R2** | R2 | Approver/Security | data + cost boundary |
| Restore from backup | R0 test | R2 production cutover | R0/R2 incident policy | SRE | restore evidence |
| Permanently destroy VM | **R2** | **R2** | R2 | Approver/SRE | verify no authoritative data |

---

## 5.4 Secret / Permission / Identity

| Action | Default Level | Human Authority | Hard Rule |
|---|---|---|---|
| Create secret logical reference | R0/R2 by scope | Platform Admin/Security | secret value不进 Domain DB |
| Generate machine credential | R0 if pre-authorized | Security policy | bounded scope + TTL |
| Rotate credential | R0 if policy-scheduled | Security | rotation evidence |
| Revoke compromised credential | R0 emergency | Security/SRE | immediate containment allowed |
| Read plaintext secret into AI context | **禁止 by default** | — | AI Operator 不应看到明文 |
| Permission request | R0 | requester | proposal only |
| Grant/revoke ordinary permission | **R2** | authorized approver | no self-escalation |
| Privileged/admin grant | **R2/R3** | security/authorized human | separation of duty |
| Change authorization policy | R1 → **R2** | policy owner | |
| Disable audit logging | **禁止** | — | 不能以 exception 放开 |
| Delete audit evidence | **禁止** | — | retention policy controls archival |

---

## 5.5 Governance / Approval / Security / License

| Action | Level | Final Authority | Notes |
|---|---|---|---|
| Generate risk summary | R0 | — | AI 可做 |
| Generate decision packet | R0 | — | AI 可做 |
| Recommend approve/reject | R1 | — | 必须标识为 AI recommendation |
| Final Approval decision | **R3** | Human Approver | AI 不可代批 |
| Security Exception proposal | R1 | — | |
| Final Security Exception decision | **R3** | authorized human | time-bounded / scoped |
| License risk detection | R0 | Security/Auditor | |
| License migration proposal | R1 | owner | |
| Final License Override decision | **R3** | authorized human/legal governance | AI 不做法律责任决定 |
| Change active Policy | R1 → R2 | policy owner/approver | |
| Lower frozen Gate to obtain PASS | **禁止** | — | 必须改 Contract/Authority 走独立流程 |
| Delete failed Evidence | **禁止** | — | 可 supersede，不可抹除 |
| Mark Evidence invalid | R1/R2 | verifier/authorized owner | 新 evidence/decision record |

---

## 5.6 Third-party Backend / Dependency

| Action | Level | Human Role | Notes |
|---|---|---|---|
| Probe backend | R0 | Platform Admin | |
| Run Adapter conformance test | R0 | Integration owner | |
| Add backend candidate | R0/R1 | Platform Admin | 不自动进入生产 |
| Enable backend in dev | R0 | Platform Admin | |
| Production backend cutover | **R2** | Approver/Admin/SRE | replacement evidence + rollback |
| Replace backend under active incident | R0/R2 by pre-authorized policy | SRE | LKG/failover policy |
| Change upstream dependency revision | R0 non-prod | **R2 prod** | owner/security | SBOM + compatibility |
| Continue after critical license risk | **R3 override decision** | authorized human | 默认迁移/阻断 |
| Introduce closed-source dependency into critical path | R1 → **R2/R3** | architecture/security/business | Exit Path mandatory |

---

## 5.7 Workflow / Agent / Tool

| Action | Level | Notes |
|---|---|---|
| AI generates plan | R0 | |
| AI decomposes tasks | R0 | |
| AI calls read-only Tool | R0 | inherited permission |
| AI calls reversible low-risk mutation | R0 | policy + scope + budget |
| AI calls production mutation | R2 unless explicitly pre-authorized bounded policy | |
| AI requests Approval | R0 | |
| AI approves own request | **禁止** | |
| AI expands its own permissions | **禁止** | |
| AI changes active Policy | R1/R2 | cannot self-approve |
| AI retries failed operation | R0 within retry budget | retry limit required |
| AI exceeds retry/budget boundary | R1/R2 | human intervention |
| AI performs destructive delete | R2 | decision packet + post-check |
| AI bypasses Tool/Adapter and calls backend admin API | **禁止** | no hidden side channel |

---

# 6. 八个冻结重点动作

WBS 指定的八项动作正式收敛如下。

## 6.1 Production Promotion

**Default: R2 — HUMAN_APPROVAL_REQUIRED**

AI 可以：

- 准备 promotion plan；
- 收集 Evaluation/Evidence；
- 计算 diff；
- 生成 rollback plan；
- 提交 Approval。

人批准后，AI/System 可以执行：

- canary；
- progressive rollout；
- verification；
- rollback if guard fails。

AI 不可：

- 自己批准；
- 为获得 PASS 修改 Gate；
- 忽略缺失 Evidence。

---

## 6.2 Secret

分拆处理：

### secret lifecycle

create / generate / rotate / revoke：

- 在预授权 policy 内可 R0；
- 高权限或生产 root credential 默认 R2。

### secret plaintext access

AI Operator：

> **默认禁止读取明文 Secret。**

应该通过：

- secret reference；
- brokered credential；
- short-lived token；
- tool-side injection。

避免 Secret 进入 prompt/log/evidence。

---

## 6.3 Permission

Grant / privilege elevation：

**Default: R2**

privileged/admin elevation 可升级 R3 human decision。

Hard rule：

```text
AI cannot grant itself more authority.
```

---

## 6.4 Data Export

- 普通、内部、低敏、已授权：R0；
- 敏感/跨 scope：R2；
- 外部/跨境/受严格治理数据：R2/R3 按 Policy。

Decision Packet 必须显示：

- what；
- why；
- destination；
- classification；
- amount；
- retention；
- expiry；
- legal/license constraints。

---

## 6.5 Model Publish

- internal candidate publish：R0；
- internal production promotion：R2；
- external/public publish：R2；
- 存在 license/security exception：进入对应 R3 decision。

---

## 6.6 License Override

**Final decision: R3 — HUMAN_ONLY**

AI 可以：

- 识别冲突；
- 找替代方案；
- 生成 migration plan；
- 估算影响；
- 准备 legal/license evidence。

AI 不可：

- 宣称 override 合法；
- 自己接受 license 风险。

---

## 6.7 Security Exception

**Final decision: R3 — HUMAN_ONLY**

Exception 必须：

- scope-bound；
- reasoned；
- evidence-backed；
- time-bounded；
- have owner；
- have expiry；
- have remediation plan。

AI 可以自动提醒 expiry，但不能自行延长 exception。

---

## 6.8 Destructive Delete

**Default: R2**

包括：

- canonical Dataset；
- ModelAsset authoritative metadata；
- production Deployment final teardown；
- VM with authoritative data；
- primary Artifact；
- Policy history。

必须先：

```text
impact analysis
→ lineage check
→ retention/legal check
→ backup/restore check
→ approval
→ delete
→ verification
→ tombstone/audit
```

Derived Index/Cache 的删除不等同 destructive delete，可按 R0。

---

# 7. Pre-authorized Automation

为了避免平台“什么都要点批准”，允许建立预授权 Policy。

例如：

```text
Policy:
  Environment = Production
  Action = rollback_to_lkg
  Trigger = error_rate > threshold for 5m
  Target = current deployment only
  Max executions = 1
  Rollback target = approved LKG
  Evidence = required
  Notify = SRE + owner
```

满足该 policy 时：

```text
Production rollback
R2 at policy creation time
→ R0 at runtime
```

这就是：

> 人批准规则，而不是人逐次批准每个自动化动作。

---

# 8. Emergency Authority

故障时不能把“紧急”当万能越权理由。

Emergency Policy 必须预先定义：

- who/what can trigger；
- allowed actions；
- scope；
- max duration；
- max blast radius；
- LKG target；
- required evidence；
- mandatory notification；
- post-incident review。

允许的典型自动动作：

- revoke compromised credential；
- isolate unhealthy node；
- rollback to approved LKG；
- stop runaway workload；
- disable unhealthy backend；
- drain resource。

不允许因 emergency 自动：

- 降低 Security Gate；
- 删除 audit；
- 批准 license override；
- 永久扩大权限。

---

# 9. Separation of Duty

第一轮强制关注：

```text
requester != approver
```

适用于：

- privileged permission；
- Security Exception；
- License Override；
- destructive production delete；
- high-risk Production Promotion。

是否允许同一人兼任不同 Role 不重要。

关键是：

> 同一个具体高风险 transaction 是否允许 self-approval。

由 Policy 控制。

---

# 10. Decision Packet Contract

凡 R2/R3，Approval Inbox 至少必须展示：

```text
Action
Subject
Requested by
Proposed by (AI/User)
Environment
Scope
Before
After
Why
Evidence
GateResult
Policy
Risk
Blast Radius
Cost/Budget
Data/License/Security Impact
Rollback / LKG
Expiry
Execution Plan
Post-condition Check
```

Approver 不应为了理解一次批准而必须：

- 登录 MLflow；
- 登录 Harbor；
- 登录 libvirt；
- 看 raw SGLang logs；
- 问 Agent “你刚刚做了什么”。

第三方细节可以 drill-down，但主决策信息必须在 Control Hub 内完整。

---

# 11. AI Operator UI Contract

AI Operator 每次准备产生真实副作用时，UI 必须明确显示：

### 11.1 当前 Authority

```text
Acting as:
Role:
Scope:
Environment:
Effective policy:
```

### 11.2 动作等级

```text
AI_CAN_EXECUTE
AI_CAN_PROPOSE_ONLY
HUMAN_APPROVAL_REQUIRED
HUMAN_ONLY
BLOCKED
```

### 11.3 副作用

例如：

```text
Will create:
Will update:
Will stop:
Will delete:
Will expose externally:
Estimated GPU/API cost:
```

### 11.4 Evidence

说明：

- execution evidence 将写到哪里；
- failure 如何记录；
- rollback/LKG 是什么。

### 11.5 禁止模式

AI Operator 不能：

- 隐藏 Approval；
- 用 Command Palette 绕过页面 Gate；
- 用 backend admin API 绕过 Adapter；
- 将“建议”渲染成“系统已经决定”；
- 将 AI recommendation 与 GateResult 混为一个状态。

---

# 12. Needs Your Attention 规则

只有真正需要当前用户行动的事项进入高优先级 Attention。

## Approver

显示：

- pending R2/R3；
- evidence changed after request；
- approval expiring；
- request invalidated。

## SRE

显示：

- incident requiring R2；
- auto-recovery exhausted；
- rollback blocked；
- capacity policy needs change。

## Security/Auditor

显示：

- critical dependency/license risk；
- exception expiry；
- permission escalation；
- missing audit evidence。

## AI/Data Engineer

显示：

- Gate FAIL/BLOCKED；
- data classification conflict；
- candidate waiting approval；
- required evidence missing。

---

# 13. Failure Handling

AI action 失败时，不允许无限重试。

通用规则：

```text
Attempt
→ failure classified
→ bounded retry
→ recovery action
→ bounded retry
→ escalate / block
```

进入 R2/R3 的典型条件：

- retry budget exhausted；
- uncertainty increased；
- state cannot be reconciled；
- rollback target unavailable；
- authority conflict；
- unexpected destructive side effect；
- security/license/data boundary changed。

失败 Evidence 保留。

---

# 14. Policy Tightening / Loosening

下层 Policy：

- 可以把 R0 提升到 R1/R2/R3；
- 可以缩小 scope；
- 可以降低 budget；
- 可以要求更多 Evidence。

下层 Policy **不能静默降低 Frozen minimum**。

例如：

```text
Production Promotion = minimum R2
```

普通项目 Policy 不可以改成 R0。

若确需改变 Frozen minimum：

> 必须走上位 Contract / Architecture Change，而不是项目配置。

---

# 15. Golden Journey 输入

本矩阵直接约束下一 WP。

## Journey 1 — 外部模型接入上线

```text
discover/import/probe/benchmark = R0
candidate deployment           = R0
promotion proposal             = R1
production promotion           = R2
```

## Journey 2 — Dataset → Training

```text
ingest/clean/profile           = R0
sensitive classification      = R2
training within budget         = R0
high-cost training            = R2
external data transfer        = R2
```

## Journey 3 — Research Reproduction

```text
plan/reproduce/evaluate        = R0
high-cost / restricted inputs  = R2
integration recommendation    = R1
```

## Journey 4 — Knowledge/RAG

```text
ingest/index/rebuild           = R0
sensitive export              = R2
publish production capability = R2
```

## Journey 5 — GPU Scheduling

```text
placement/autoscale inside policy = R0
change policy                     = R2
raise global budget               = R2
```

## Journey 6 — Candidate → Production

核心 Gate = R2。

## Journey 7 — Backend Replacement

```text
probe/compat test    = R0
migration plan       = R1
production cutover   = R2
```

## Journey 8 — License Risk Migration

```text
detect risk          = R0
migration plan       = R1
override decision    = R3
cutover              = R2
```

## Journey 9 — Agent + Human Approval

完整展示 R0/R1/R2/R3 转换。

## Journey 10 — Recover to LKG

预授权 recovery policy 内 R0；否则 R2。

---

# 16. Low-fi 验收问题

后续 Low-fi 必须能回答：

1. 用户是否一眼知道当前动作是 R0/R1/R2/R3？
2. AI 是在“建议”还是“即将执行”？
3. 为什么需要审批？
4. Approver 是否看得到 before/after？
5. Evidence 是否完整？
6. rollback/LKG 是否明确？
7. 当前操作的 scope/environment 是否明确？
8. Command Palette 是否遵守同一责任等级？
9. AI Operator 是否继承当前用户 Authority？
10. AI 是否可能看到明文 Secret？
11. destructive delete 是否与普通 delete 明显区分？
12. emergency action 是否显示预授权 Policy？
13. approval 后实际执行是否再次做 Policy re-check？
14. execution 后是否生成 post-condition Evidence？

---

# 17. Acceptance Criteria

WP-P2-02 完成条件：

- [x] 定义四级 Human-AI Responsibility；
- [x] 明确责任等级由 action + scope + environment + risk + policy + evidence 联合决定；
- [x] 覆盖 Production Promotion；
- [x] 覆盖 Secret；
- [x] 覆盖 Permission；
- [x] 覆盖 Data Export；
- [x] 覆盖 Model Publish；
- [x] 覆盖 License Override；
- [x] 覆盖 Security Exception；
- [x] 覆盖 Destructive Delete；
- [x] 定义 pre-authorized automation；
- [x] 定义 emergency authority；
- [x] 定义 separation of duty；
- [x] 定义 Approval Decision Packet；
- [x] 定义 AI Operator UI contract；
- [x] 明确 AI 不可 self-approve / self-escalate；
- [x] 明确普通 Policy 只能收紧 Frozen minimum，不能静默放宽。

---

# 18. Exit Condition

WP-P2-02 Exit Condition：

> 后续 Golden Journey、IA、Low-fi 不需要临时猜测“AI 到底能不能做这一步”，每个关键动作都可以根据本责任模型得到明确的执行、建议、审批或人类决策路径。

下一步进入：

```text
WP-P2-03 Golden Journeys
        ↓
WP-P2-04 Information Architecture
        ↓
WP-P2-05 Low-fi Wireframes
```

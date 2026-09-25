# User Roles v0.1

> Work Package: **WP-P2-01 — User Roles**  
> Status: **FIRST PASS FROZEN FOR JOURNEY / IA INPUT**  
> Authority: `docs/design/00-FUNCTIONAL-ARCHITECTURE.md`, `docs/design/01-TECHNOLOGY-STACK.md`, `docs/design/02-WORK-BREAKDOWN.md`  
> Date: **2026-09-25**  
> Purpose: 先冻结“谁在使用平台、为什么来、允许做什么、必须看到什么”，作为 Golden Journeys、IA、Low-fi 和 Human-AI Responsibility Matrix 的共同输入。

---

## 1. 角色设计原则

本文件定义的是 **Product Role / Responsibility Role**，不是数据库权限表，也不是最终 RBAC implementation。

角色必须遵守：

```text
Role
  ↓
Goal / Responsibility
  ↓
Allowed Product Actions
  ↓
Approval Boundary
  ↓
Evidence / Audit
```

而不是：

```text
页面菜单
  ↓
反推一个“管理员”
```

### 1.1 核心原则

1. **Platform Admin 不是超级审批人**  
   管理平台配置，不自动拥有 Security Exception、License Override、Production Promotion 的最终批准权。

2. **Operator / SRE 不是模型所有者**  
   可以恢复、扩缩、回滚、处置运行故障，但不能无证据改模型质量 Gate。

3. **AI Engineer 不是基础设施管理员**  
   负责模型/能力工程，不直接持有宿主机、Secret、全局权限。

4. **Approver 是作用域角色，不是固定职位**  
   某人可在特定 Domain/Project/Environment 上拥有批准权。

5. **Security / Auditor 要能独立观察**  
   审计证据不能依赖被审计人自己生成的不可验证摘要。

6. **Viewer 真正只读**  
   不允许因为“看详情”触发副作用。

7. **AI Operator 是跨角色助手，不是第十个人类角色**  
   它根据当前用户权限执行/建议；永远不能借 AI 提升用户 Authority。

---

## 2. 第一批角色总览

| Role | 核心目标 | 主要对象 | 默认权限姿态 | 典型风险 |
|---|---|---|---|---|
| Platform Admin | 让平台本身可用、可配置、可演进 | Environment, Provider, Adapter, Policy, platform config | 管理型，高权限但受审批约束 | 误把“平台管理员”变成全权批准人 |
| AI Engineer | 把模型变成可验证 Capability | ModelAsset, Runtime, Deployment, EvaluationRun | 工程写权限 | 绕过 Gate 直接上线 |
| Data / Knowledge Engineer | 让数据/知识可追溯、可用、可重建 | DatasetAsset, KnowledgeAsset, Index | 数据写权限 | 数据污染、ACL/License 漏失 |
| Researcher | 复现、比较、形成 Evidence | Experiment, EvaluationRun, Evidence | 实验写权限 | 把实验结论直接当生产结论 |
| Application Developer | 安全消费平台 Capability | Capability, Provider endpoint, Tool | 消费/集成权限 | 绑定具体 runtime/provider |
| Operator / SRE | 保持服务健康并快速恢复 | Node, GPU, VM, Deployment, Environment | 运行操作权限 | 为恢复服务而越过质量/安全 Gate |
| Security / Auditor | 验证合规、安全、供应链和审计链 | Policy, Evidence, Approval, Dependency | 只读为主 + 治理操作 | 与被审计对象职责冲突 |
| Approver | 对受控高风险动作做最终人类判定 | Approval, GateResult, Policy exception | 作用域批准权限 | rubber-stamp / 自批自审 |
| Viewer | 获取状态、证据和结果 | 全部可见对象的只读视图 | 只读 | 页面副作用/越权下载 |

---

## 3. Platform Admin

### 3.1 为什么存在

负责“平台作为平台”能够被配置、接入新后端、维护环境与治理边界，而不是负责所有模型、数据和审批工作。

### 3.2 核心目标

- 配置平台级环境与基础资源；
- 注册/启停 Provider、Adapter、Backend；
- 管理全局 feature/config boundary；
- 管理项目/环境的基础访问边界；
- 维护平台级默认 Policy；
- 观察平台整体健康；
- 发起但不自动批准高风险变更。

### 3.3 主要对象

`Environment`, `Provider`, `Adapter`, `UpstreamDependency`, `Policy`, `Node`, `VM`。

### 3.4 允许做

- 注册新 Provider / Adapter；
- 配置 endpoint、capacity、environment binding；
- 创建环境；
- 启用/禁用非生产 backend；
- 管理基础平台参数；
- 查看全部 platform health / audit summary；
- 发起 dependency replacement；
- 发起权限变更请求。

### 3.5 不应默认拥有

- Production Promotion 最终批准；
- License Override；
- Security Exception；
- 导出敏感 Dataset；
- 删除审计 Evidence；
- 读取明文 Secret；
- 自己提出并批准同一个高风险动作。

### 3.6 AI Operator 对该角色

**可执行**：inventory、health check、配置差异检查、生成变更计划、非高风险配置草案。  
**仅建议**：权限变更、Secret rotation policy、backend replacement cutover。  
**需人工批准**：生产 backend 切换、权限提升、破坏性删除、安全例外。

### 3.7 Home / Needs Your Attention

必须突出：

- Adapter/backend unhealthy；
- dependency risk；
- capacity exhaustion；
- pending approval；
- configuration drift；
- failed restore/rebuild evidence。

---

## 4. AI Engineer

### 4.1 为什么存在

负责从模型资产到可验证 Capability 的工程闭环。

### 4.2 核心目标

- 导入/注册模型；
- 选择 Runtime；
- 构造 Deployment candidate；
- Benchmark / Evaluation；
- 量化/导出；
- 形成 Capability；
- 将 candidate 提交 Production Gate。

### 4.3 主要对象

`ModelAsset`, `Capability`, `Runtime`, `Deployment`, `EvaluationRun`, `Evidence`, `GateResult`。

### 4.4 允许做

- Model intake；
- 创建 runtime profile；
- 创建 candidate deployment；
- 发起 benchmark/evaluation；
- 比较 SGLang/vLLM/llama.cpp/BentoML implementation；
- 创建 logical capability mapping；
- 查看 GPU fit / cost / quality evidence；
- 发起 Production Promotion。

### 4.5 不应默认拥有

- 绕过 Gate 的 Production Promotion；
- 修改全局 Security Policy；
- 直接读取 Secret；
- 修改 Node/VM host-level config；
- 访问无授权 Dataset；
- 删除失败实验 Evidence。

### 4.6 AI Operator 对该角色

**可执行**：生成实验计划、跑允许的 benchmark、收集 evidence、比较 Pareto、准备 deployment candidate。  
**仅建议**：模型替换、量化策略、production promotion。  
**需人工批准**：正式上线、license exception、受限数据进入外部 Provider。

### 4.7 Home / Needs Your Attention

- evaluation regression；
- runtime incompatibility；
- pending candidate gate；
- model license/security risk；
- production capability quality drift；
- failed deployment / rollback recommendation。

---

## 5. Data / Knowledge Engineer

### 5.1 为什么存在

负责把原始数据变成可治理 Dataset、Knowledge 与可重建 Index。

### 5.2 核心目标

- Dataset intake；
- data classification；
- lineage；
- 清洗/去重/标注；
- Knowledge ingestion；
- chunk/index recipe；
- embedding/search index rebuild；
- 数据质量与 License evidence。

### 5.3 主要对象

`DatasetAsset`, `KnowledgeAsset`, `Index`, `Artifact`, `Evidence`, `Policy`。

### 5.4 允许做

- 导入 Dataset；
- 定义 metadata/lineage；
- 启动清洗、OCR/ASR、标注、去重；
- 建立 KnowledgeAsset；
- 构建/rebuild Index；
- 生成 Gold Set 候选；
- 标记数据许可/来源；
- 提交数据发布/导出请求。

### 5.5 不应默认拥有

- 绕过 Data Export approval；
- 去掉 source/license attribution；
- 把 benchmark/evaluation data 静默混入训练集；
- 让 vector/search index 成为唯一事实源；
- 未授权向外部 Provider 发送受限数据。

### 5.6 AI Operator 对该角色

**可执行**：数据 profiling、dedupe proposal、OCR/ASR pipeline、index rebuild、质量检查。  
**仅建议**：自动标注接受、数据分类变更、训练集纳入。  
**需人工批准**：敏感数据导出、license override、跨边界共享。

### 5.7 Home / Needs Your Attention

- lineage missing；
- index stale；
- source/license unknown；
- sensitive data policy conflict；
- ingestion failure；
- dataset quality regression。

---

## 6. Researcher

### 6.1 为什么存在

负责“提出假设 → 复现 → 对比 → 形成 Evidence”，不直接承担生产运维。

### 6.2 核心目标

- 复现论文/GitHub 项目；
- 建立 baseline；
- experiment contract；
- ablation；
- benchmark；
- 研究报告；
- 形成可进入工程候选池的成果。

### 6.3 主要对象

`Experiment`, `TrainingRun`, `EvaluationRun`, `Artifact`, `Evidence`, `UpstreamDependency`。

### 6.4 允许做

- 创建隔离实验；
- pin exact upstream revision；
- 申请 GPU budget；
- 运行 reproduction；
- 记录参数、环境、结果；
- 对比 baseline；
- 提交 integration candidate。

### 6.5 不应默认拥有

- 将实验 endpoint 暴露为生产服务；
- 修改生产 SLA/Policy；
- 使用未授权生产数据；
- 把 paper claim 当作已验证 Evidence；
- 删除 negative result。

### 6.6 AI Operator 对该角色

**可执行**：搜集允许的上游信息、生成 reproduction plan、环境检查、批量实验、结果汇总。  
**仅建议**：结论、因果解释、是否值得集成。  
**需人工批准**：高成本实验、受限数据、正式集成/上线。

### 6.7 Home / Needs Your Attention

- reproducibility failure；
- baseline mismatch；
- budget nearing limit；
- upstream revision/license drift；
- evidence incomplete。

---

## 7. Application Developer

### 7.1 为什么存在

让业务应用只消费稳定 Capability / Unified API，而不理解 GPU、Runtime、Provider 内部细节。

### 7.2 核心目标

- 查找可用 Capability；
- 获取开发环境凭据/SDK；
- 集成 `/v1`；
- 定义 SLA/usage expectation；
- 查看 usage/error/compatibility；
- 进行非生产测试。

### 7.3 主要对象

`Capability`, `Deployment` 的只读抽象、`Provider` 的逻辑视图、`Tool`。

### 7.4 允许做

- 浏览 AI Hub；
- 选择 logical capability；
- 创建 app binding；
- 请求 quota；
- 在 dev/staging 调用；
- 查看 API contract / examples；
- 上报质量/延迟反馈。

### 7.5 不应默认拥有

- 选择具体 GPU；
- 固定内部端口；
- 依赖 SGLang/vLLM/LiteLLM DTO；
- 查看 backend Secret；
- 修改 Production deployment；
- 绕过 quota/policy。

### 7.6 AI Operator 对该角色

**可执行**：生成 SDK 示例、contract-compatible request、测试用例、错误诊断。  
**仅建议**：Capability 选择、成本/延迟折中。  
**需人工批准**：提升 quota、访问受限模型/数据。

### 7.7 Home / Needs Your Attention

- contract deprecation；
- quota nearing limit；
- capability incident；
- breaking behavior candidate；
- migration notice。

---

## 8. Operator / SRE

### 8.1 为什么存在

负责运行态可靠性、容量、故障恢复和 LKG 回滚。

### 8.2 核心目标

- health / SLO；
- Node/GPU/VM/Runtime 监控；
- incident response；
- autoscaling；
- drain/maintenance；
- rollback；
- restore/rebuild；
- evidence capture。

### 8.3 主要对象

`Resource`, `Node`, `GPU`, `VM`, `Environment`, `Runtime`, `Deployment`, `Evidence`。

### 8.4 允许做

- 查看 live topology；
- drain node/GPU；
- 重启/恢复受控 workload；
- 执行已批准 rollback；
- 切到 LKG；
- 触发 health probe；
- 执行 restore test；
- 生成 incident evidence；
- 启动 emergency proposal。

### 8.5 不应默认拥有

- 降低质量 Gate；
- 修改模型评测阈值；
- Security Exception 自批；
- 删除失败日志；
- 长期改变 Production policy 而不走 change/approval；
- 将临时 incident workaround 变成 silent baseline。

### 8.6 AI Operator 对该角色

**可执行**：诊断、日志关联、health probe、已授权 restart、自动 rollback 条件执行。  
**仅建议**：容量变更、backend failover、incident root cause。  
**需人工批准**：高风险 failover、不可逆维护、安全边界变更。

### 8.7 Home / Needs Your Attention

- SLO burn；
- GPU/node unhealthy；
- stuck workflow；
- rollback available；
- capacity saturation；
- backup/restore evidence stale。

---

## 9. Security / Auditor

### 9.1 为什么存在

提供与 Builder/Operator 分离的安全、License、供应链、权限和审计视角。

### 9.2 核心目标

- 审查权限/Policy；
- 供应链与 SBOM；
- license compliance；
- secret access evidence；
- security exception；
- data movement；
- audit trail completeness；
- release evidence review。

### 9.3 主要对象

`Policy`, `Approval`, `Evidence`, `GateResult`, `UpstreamDependency`, `Artifact`。

### 9.4 允许做

- 查看全链路 audit；
- 查看 dependency/license/security evidence；
- 标记风险；
- 发起阻断建议；
- 创建 security review；
- 验证 exception expiry；
- 审查 data export / secret access evidence。

### 9.5 不应默认拥有

- 修改实验结果；
- 代替业务 owner 发布模型；
- 直接读取不必要的明文 secret；
- 删除/重写 audit；
- 因审计便利获得不受约束的写权限。

### 9.6 AI Operator 对该角色

**可执行**：evidence correlation、policy diff、SBOM/license scan、audit gap detection。  
**仅建议**：风险等级、exception remediation。  
**需人工批准**：Security Exception、License Override、权限提升。

### 9.7 Home / Needs Your Attention

- unsigned artifact；
- license conflict；
- policy violation；
- overdue exception；
- missing audit evidence；
- suspicious privilege change。

---

## 10. Approver

### 10.1 为什么存在

对不可由系统自行承担责任的动作提供可审计的人类最终判定。

### 10.2 核心目标

处理被明确路由到本人作用域的 Approval。

### 10.3 主要对象

`Approval`, `GateResult`, `Policy`, `Evidence`。

### 10.4 允许做

- approve；
- reject；
- request changes；
- delegate（仅在 policy 允许时）；
- 查看完整 decision packet；
- 要求补证据。

### 10.5 不应默认拥有

- 修改 underlying evidence；
- 通过“审批”自动获得资源/Secret/数据写权限；
- 批准超出 scope 的事项；
- 在禁止 self-approval 的流程中批准自己发起的请求。

### 10.6 AI Operator 对该角色

**可执行**：汇总 decision packet、列出 evidence、展示 diff/风险/回滚路径。  
**不能代批**：AI 不代表 Approver 点击最终批准。  
**可建议但必须标注**：AI recommendation 必须与原始 Evidence 分开显示。

### 10.7 Approval Inbox 必须展示

- 谁发起；
- 为什么需要批准；
- 变更前/后；
- Evidence；
- Policy/Gate 命中项；
- blast radius；
- rollback/LKG；
- expiry；
- related dependency/license/security risk；
- approve/reject 后会发生什么。

---

## 11. Viewer

### 11.1 为什么存在

让管理者、协作者、审阅者在没有操作权限时仍能获得可信状态与 Evidence。

### 11.2 核心目标

- 查看平台状态；
- 查看公开/授权的资产；
- 查看实验/部署/治理结果；
- 查看 Evidence；
- 读取报告与 lineage。

### 11.3 主要对象

所有被授权对象的 read model。

### 11.4 允许做

- search；
- filter；
- view；
- compare；
- download 仅限 policy 允许的非敏感报告/导出物。

### 11.5 不允许

- 任何状态变更；
- 通过“预览/导出”绕过 Data Export；
- 触发训练/部署/重建；
- 生成带真实副作用的 command；
- 查看 secret。

### 11.6 AI Operator 对该角色

仅允许：

- 查询；
- 汇总；
- 解释；
- 比较；
- 生成无副作用的建议。

AI Operator 必须继承 Viewer 的只读边界。

---

## 12. 多角色组合规则

现实中一个人可以同时承担多个 Product Role，但权限计算必须显式。

### 12.1 允许的常见组合

```text
AI Engineer + Researcher
Data Engineer + Researcher
Platform Admin + Operator/SRE
Security/Auditor + Viewer
Approver + 其他业务角色（受 separation-of-duty 限制）
```

### 12.2 不能因组合自动放宽的边界

```text
Proposal + Approval
Security Exception request + approval
License Override request + approval
Destructive Delete request + approval
Production Promotion request + approval
```

是否允许 self-approval 必须由 Policy 明确，而不是由 UI 猜测。

### 12.3 临时权限

高风险临时权限应支持：

- reason；
- scope；
- issuer；
- approver；
- start/end；
- auto-expire；
- audit evidence。

---

## 13. 角色到一级导航的第一轮映射

此表只是 IA 输入，不冻结最终菜单可见性。

| Role | Home | AI Hub | Build | Run | Improve | Knowledge | Compute | Govern |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Platform Admin | 主 | 次 | 次 | 主 | 次 | 次 | 主 | 主 |
| AI Engineer | 主 | 主 | 主 | 主 | 主 | 次 | 次 | 次 |
| Data / Knowledge Engineer | 主 | 主 | 主 | 次 | 次 | **主** | 次 | 次 |
| Researcher | 主 | 主 | **主** | 次 | **主** | 次 | 次 | 次 |
| Application Developer | 主 | **主** | 次 | 次 | 次 | 次 | 弱 | 弱 |
| Operator / SRE | **主** | 次 | 弱 | **主** | 次 | 弱 | **主** | 主 |
| Security / Auditor | **主** | 次 | 弱 | 次 | 次 | 次 | 次 | **主** |
| Approver | **主** | 次 | 弱 | 次 | 次 | 次 | 弱 | **主** |
| Viewer | 主 | 主 | 只读 | 只读 | 只读 | 只读 | 只读 | 只读 |

说明：

- “主”表示高频工作区；
- “次”表示常用但不是首要；
- “弱”表示偶尔需要；
- “只读”表示可以看，但所有 mutation control 隐藏/禁用并有明确原因。

---

## 14. 全局入口对角色的意义

### Needs Your Attention

不是统一告警列表，而是基于角色作用域过滤：

- Admin：backend/config/dependency；
- Engineer：model/eval/deployment；
- Data：lineage/license/index；
- SRE：incident/SLO/capacity；
- Security：policy/audit/license；
- Approver：pending decisions；
- Viewer：仅显示需要知悉、无操作要求的事项。

### Global Search

返回的是我方 Domain Objects，不返回第三方裸 DTO。

### AI Operator

必须显示：

- 当前用户身份；
- 当前作用域；
- 当前 AI 可执行权限；
- 哪一步需要 Approval；
- 即将产生的副作用；
- Evidence 将写到哪里。

### Notifications

按对象/风险/作用域订阅，不能把所有 backend event 原样倾倒给用户。

### Command Palette

命令必须经过同一 Authorization / Policy / Approval pipeline，不能成为绕过页面 Gate 的捷径。

---

## 15. P2-02 Human-AI Responsibility Matrix 的直接输入

下一 WP 需要至少把以下动作逐项分类为：

```text
AI can execute
AI can propose only
Human approval required
Human only
```

第一批动作：

- Production Promotion；
- Secret create/read/rotate/revoke；
- Permission grant/revoke；
- Data Export；
- Model Publish；
- License Override；
- Security Exception；
- Destructive Delete；
- LKG rollback；
- emergency failover；
- new Provider onboarding；
- backend replacement cutover；
- dataset classification change；
- high-cost training/experiment；
- production quota change。

分类必须同时考虑：

```text
Role
+ Environment
+ Resource Scope
+ Risk
+ Policy
+ Evidence
```

不得只做一张“AI 可以/不可以”的静态表。

---

## 16. WP-P2-03 Golden Journeys 的直接输入

角色作为 Journey actor 的第一轮映射：

| Golden Journey | Primary Actor | Supporting Roles | Required Human Gate |
|---|---|---|---|
| 外部模型接入并上线 | AI Engineer | Admin, SRE, Security | Production Promotion |
| Dataset 导入并训练 | Data Engineer + AI Engineer | Researcher, Security | 敏感数据/高成本/生产发布按 Policy |
| 复现论文/GitHub | Researcher | AI Engineer, Admin | 高成本/受限数据 |
| Knowledge/RAG Capability | Data Engineer | AI Engineer, App Developer | 受限数据发布 |
| GPU 高峰/低谷调度 | Operator/SRE | Admin | Policy 变更需批准；正常自动调度不逐次批准 |
| Candidate → Production | AI Engineer | SRE, Security | Approver |
| Backend 替换 | Platform Admin | SRE, affected engineers | Cutover Approval |
| License 风险迁移 | Security/Auditor | Admin, Engineer | Exception 或 Migration Approval |
| Agent 自动执行 + 人审 | 任一业务角色 | Approver | 按 action risk |
| 故障恢复到 LKG | Operator/SRE | Admin, service owner | 预授权策略内可自动；越界需批准 |

---

## 17. Low-fi 设计约束

后续 Wireframe 必须验证以下角色问题，而不是只验证“页面好不好看”：

1. 用户一进入 Home 能否知道 **现在需要自己处理什么**？
2. 用户能否区分 **Candidate / Production / Failed / LKG**？
3. 用户能否知道某个结果的 **Evidence 来自哪里**？
4. 用户能否看出 **AI 正在建议，还是已经被授权执行**？
5. 用户能否知道某动作是否需要 Approval？
6. Approver 能否在不打开第三方系统的情况下完成判断？
7. SRE 能否在 incident 中快速找到 rollback/LKG？
8. App Developer 是否完全不需要理解具体 GPU/runtime/provider？
9. Security/Auditor 是否能独立复核 lineage/license/policy？
10. Viewer 是否不存在任何隐蔽 mutation path？

---

## 18. Acceptance Criteria

WP-P2-01 完成条件：

- [x] 覆盖冻结要求的 9 个首批角色；
- [x] 每个角色定义目标、对象、允许做、不应默认做、AI 边界、Attention；
- [x] Platform Admin 与 Approver 分离；
- [x] Operator/SRE 与质量 Gate Authority 分离；
- [x] Security/Auditor 保持独立审计视角；
- [x] Viewer 明确无副作用；
- [x] AI Operator 被定义为继承人类权限的跨角色助手，而非超级角色；
- [x] 提供 Roles → IA 输入；
- [x] 提供 Roles → Human-AI Matrix 输入；
- [x] 提供 Roles → Golden Journeys 输入；
- [x] 为 Low-fi 给出可验收问题。

---

## 19. 本 WP 不做什么

本文件不冻结：

- 最终 RBAC schema；
- IAM provider；
- 用户/组织数据库表；
- 最终 permission strings；
- 最终导航显隐规则；
- Human-AI 动作逐项判定；
- Golden Journey 详细步骤；
- High-fi 视觉风格。

这些分别属于后续 P1/P2 Work Package。

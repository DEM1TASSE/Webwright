# Web Skill Factory：从 Workflow 复用到 Site Primitive 复用

> 本文档用于实习结束 presentation。内容已经按“可以直接拆成 PPT”的形式组织，包含主线、
> pipeline、实现细节、实验数字、逐页文案、讲稿、图示建议和备选问答。

## 0. 推荐的 presentation 主线

整个 presentation 只需要回答三个问题：

1. 过去如何复用完整 workflow？
2. 为什么 cross-template task 需要更细粒度的 primitive？
3. primitive pipeline 如何构建、检索和使用，结果如何？

推荐用这一条故事线：

```text
Web Skill Factory
  将成功执行蒸馏成完整 workflow skill
                  ↓
Same-template reuse 很自然
Cross-template adaptation 粒度过粗
                  ↓
把跨 template 共享的站点操作抽成 primitive
                  ↓
按网站构建 object-oriented primitive package
                  ↓
metadata retrieval → use/adapt/skip → full-code injection
                  ↓
Clean paired WebArena pilot:
45.8% → 54.2% success rate
```

一句话 contribution：

> We extend Web Skill Factory from workflow-level reuse to site-scoped primitive reuse for
> cross-template tasks on the same website.

一句话结果：

> On a clean paired 24-task WebArena pilot, primitive reuse improves success from 45.8% to
> 54.2%, while reducing counted agent-execution steps from 9.58 to 8.50.

---

## 1. 术语与实验范围

### 1.1 Task instance、template 与 website

```text
Website
└── Task template
    ├── Task instance 1
    ├── Task instance 2
    └── Task instance 3
```

- **Task instance**：一个具体任务，例如查询某个具体项目的 commits。
- **Task template**：共享同一任务结构、仅参数不同的一组任务。
- **Website**：GitLab、Shopping、Shopping Admin、Map 等站点。

### 1.2 三种复用范围

| 复用范围 | source 与 target 的关系 | 最合适的复用单元 |
|---|---|---|
| Same instance | 完全相同任务 | 直接 replay |
| Same template | 参数不同、流程形状相同 | 完整参数化 workflow |
| Cross template, same website | 任务目标不同，但共享站点操作 | site primitive |

本工作的目标是第三种：

> **Cross-template reuse within the same website.**

训练 template 与测试 template 不重合，但二者来自相同 website。

### 1.3 Workflow 与 primitive 的边界

Workflow 负责完整任务策略：

```text
登录 → 找项目 → 打开 commits → 按作者过滤 → 按日期过滤 → 统计 → 格式化答案
```

Primitive 只负责稳定的站点操作：

```text
login_customer_account(...)
get_project_by_path(...)
list_repository_commits(...)
get_order_detail(...)
search_product_reviews(...)
```

Task-specific filtering、ranking、aggregation 和最终格式仍由当前任务的 agent 完成。

---

## 2. Pipeline A：Workflow-level Web Skill Factory

## 2.1 原始问题

Web agent 在任务成功后会产生一个完整的 `final_script.py`。如果不复用，新的任务需要重新发现：

- 如何登录；
- 页面或 API 在哪里；
- DOM、URL、字段和分页结构；
- 如何抽取并格式化答案。

Web Skill Factory 将成功执行蒸馏成可复用、可维护的 workflow skill。

## 2.2 Workflow 建库流程

```text
Successful agent executions
        ↓
Gold/evaluator admission
        ↓
Group executions by task template
        ↓
Compare different task instances
        ↓
Identify varying parameters and stable patterns
        ↓
Distill one standalone parameterized workflow
        ↓
Workflow Skill Library
```

更具体地：

```text
Task A1: repo=x, author=Alice, date=d1
Task A2: repo=y, author=Bob,   date=d2
Task A3: repo=z, author=Carol, date=d3
                         ↓
Parameterize(repo, author, date)
                         ↓
One reusable workflow for template A
```

### 输入

- evaluator 通过的完整 agent run；
- `final_script.py`；
- task intent、template ID 和 instance parameters；
- 执行日志与结果 metadata。

### 核心更新方式

- 新 template：创建新的完整 workflow skill；
- 已存在 template：根据新增实例扩展参数与 pattern；
- 保留完整 standalone code，不依赖外部 runtime package。

### Workflow artifact

```text
workflow_library/
└── <skill_id>/
    ├── skill.py       # 完整 standalone workflow
    ├── meta.json      # template、参数、来源与 grade
    └── replays.json   # release 版本可加入 replay
```

## 2.3 Workflow consumption

```text
New task
   ↓
Retrieve workflow candidates
   ↓
Judge task/workflow fit
   ├── USE   → workflow shape directly matches
   ├── ADAPT → reuse workflow as a prior and modify it
   └── SKIP  → solve from scratch
   ↓
Standalone final script
```

### USE

- 通常对应 same-template task；
- workflow 的参数能够表达当前实例；
- 可以直接运行或做非常薄的参数替换。

### ADAPT

- target 属于不同 template；
- 完整 workflow 中有部分相关策略；
- agent 读取整个 workflow，再改写成 target task 的脚本。

### SKIP

- workflow 与当前任务不匹配；
- 注入可能造成噪声或 strategy anchoring；
- agent 从 scratch 求解。

## 2.4 为什么完整 workflow 不适合 cross-template reuse

假设 source workflow 是：

```text
login
→ locate project
→ list commits
→ filter by author
→ filter by date
→ count
```

target task 可能是：

```text
login
→ locate project
→ list commits
→ find latest commit message
```

二者共享前半段，但完整 workflow 同时带入了：

- source task 的过滤规则；
- source task 的聚合逻辑；
- source task 的输出 schema；
- source task 的策略选择。

因此 cross-template adaptation 的问题不是“完全没有可复用内容”，而是：

> **The reusable material is embedded inside a task-specific workflow.**

这就是引入 primitive 层的动机。

---

## 3. Pipeline B：Site Primitive Factory

## 3.1 核心设计

Primitive 被定义为：

> A reusable site-specific operation with a typed contract, explicit scope, and source
> provenance, used as synthesis material rather than a runtime dependency.

设计原则：

1. **Site-scoped**：primitive 属于一个 website。
2. **Cross-template**：粒度由多个 template 的共享操作决定。
3. **Typed contract**：有明确输入、输出、requires 和 provides。
4. **Task-neutral**：不包含 task-specific final selection 或答案。
5. **Provenance-grounded**：必须能追溯到 gold workflow。
6. **Copy-on-use**：retrieved code 被 vendor 到新的 standalone script。
7. **No runtime dependency**：历史 workflow 不 import 活跃 library。

## 3.2 为什么按网站构建 package

站点操作的复用边界天然受 website 约束：

- GitLab 的 URL、API 和 project semantics 只属于 GitLab；
- Shopping 的登录、订单和商品 catalog 只属于 Shopping；
- Shopping Admin 的 grid、review 与 customer record 有自己的结构；
- Map 的 geocoder 和 routing backend 有独立 contract。

因此每个 website 建一个 package：

```text
GitLabSite
├── Auth
├── Projects
├── Commits
└── Reviews

ShoppingSite
├── Auth
├── Catalog
├── Orders
└── Reviews

ShoppingAdminSite
├── Auth
├── Orders
├── Customers
└── Reviews
```

实现上仍是一个 `package.py`，feature class 用于组织与寻址；不引入复杂的跨文件继承层次。

## 3.3 Primitive artifact

每个 primitive 包含：

```json
{
  "primitive_id": "gitlab/commits/list_repository_commits",
  "method": "list_repository_commits",
  "capability": "List typed commit records for a repository",
  "input_contract": {},
  "output_contract": {},
  "requires": ["gitlab.project_context"],
  "provides": ["gitlab.commit_records"],
  "supported_patterns": [],
  "source_evidence": []
}
```

字段含义：

| 字段 | 作用 |
|---|---|
| `primitive_id` | 稳定寻址 ID |
| `method` | package 内对应方法 |
| `capability` | metadata retrieval 使用的能力描述 |
| `input_contract` | 必要参数及类型 |
| `output_contract` | typed output schema |
| `requires` | 环境或浏览器状态前置条件 |
| `provides` | 执行后提供的状态或数据 |
| `supported_patterns` | 已知适用任务模式 |
| `source_evidence` | gold workflow provenance |

`requires/provides` 是状态契约，不是代码依赖图。例如：

```json
{
  "requires": ["authenticated_session"],
  "provides": ["repository_context"]
}
```

workflow 仍显式组合：

```python
login(...)
open_repository(...)
list_repository_commits(...)
```

## 3.4 Initial build：按网站批量建库

Primitive 的边界不能只看单个 workflow，因为单个 workflow 无法区分“任务专用步骤”和“跨
template 共享步骤”。

例如：

```text
Workflow 1 = A + B
Workflow 2 = A + C
Workflow 3 = B + D
```

跨 workflow 比较后，合理 primitive 可能是 A、B，而不是把 Workflow 1 整体复制成一个
primitive。

正式实现不要求一次把该网站所有 workflow 塞进一个 prompt，而是：

```text
All gold workflows for one website
        ↓
Stable ordering by template_id and task_id
        ↓
Seeded shuffle
        ↓
Configurable batches (pilot: batch_size = 8)
        ↓
Incrementally update one site primitive pool
```

这样同时满足：

- 能通过 cross-template comparison 决定粒度；
- 支持几十到一百多个 workflow；
- prompt 不会无限增长；
- batch 顺序和随机种子可审计。

## 3.5 每个 workflow 的 extraction

首先从每个 gold workflow 提取候选操作：

```text
Gold final_script.py
        ↓
Identify site-specific reusable operations
        ↓
Separate task logic from site acquisition
        ↓
Generate typed primitive candidates
        ↓
Attach source workflow evidence
```

应该抽取：

- 登录与 session 建立；
- 稳定页面/API acquisition；
- pagination；
- site-specific parsing；
- 单位和字段语义归一化；
- 稳定实体 lookup。

不应该抽取：

- 当前任务的最终答案；
- 当前任务专用的过滤条件；
- subjective classification；
- ranking、aggregation 和输出格式；
- 硬编码 task instance。

## 3.6 Incremental update operators

每个 batch 到来时，updater 对 primitive pool 使用三个操作：

### ADD

当新 workflow 暴露了 library 尚未覆盖的、可复用站点操作：

```text
new reusable operation
→ ADD primitive
```

### UPDATE

当已有 primitive 的核心语义相同，但新 workflow 提供：

- 新参数；
- 更稳定 selector/API；
- 更完整返回字段；
- 新的 supported pattern；
- 更强 provenance；
- 更准确 contract。

则更新原 primitive，而不是创建重复函数。

### SKIP

当新 workflow：

- 只重复已有能力；
- 只包含 task-specific logic；
- 缺少足够证据；
- 会造成错误抽象；

则不修改 primitive pool。

更新阶段暂不执行 merge/split，以降低每个 batch 的判断复杂度。

## 3.7 Consolidate + Organize

所有 batch update 完成后，执行一次站点级 consolidation：

```text
Pre-consolidation primitive pool
        ↓
Merge semantic duplicates
        ↓
Split primitives with multiple independent responsibilities
        ↓
Normalize names and contracts
        ↓
Organize into feature classes
        ↓
Final candidate site package
```

包含三个元操作：

### MERGE

两个 primitive 表达相同站点操作，仅参数或字段覆盖不同，则合并为一个更完整 contract。

### SPLIT

一个 primitive 同时承担两个可以独立复用的操作，则拆分。例如：

```text
search_product_and_parse_all_reviews
                   ↓
search_products
list_product_reviews
```

### ORGANIZE

将 primitive 放入稳定的 feature class：

```text
Auth / Projects / Commits / Catalog / Orders / Reviews
```

MVP 不自动 `DROP` 历史 primitive。错误或冗余能力优先通过 consolidate/merge 处理，避免无法审计
的删除。

## 3.8 Snapshot 与 provenance

每一步都保存 snapshot：

```text
site_library/
├── config.json
├── workflow_order.json
├── extractions/
│   └── <workflow_id>/
├── batches/
│   └── batch_000/
│       ├── input.json
│       ├── proposal.json
│       ├── primitive_diff.json
│       ├── workflow_attribution.json
│       └── validation.json
├── pre_consolidation/
│   └── primitive_pool.json
├── consolidation/
│   ├── proposal.json
│   ├── coverage.json
│   └── validation.json
└── final_candidate/
    ├── package.py
    ├── index.json
    ├── primitive_pool.json
    └── review.md
```

它能回答：

- 哪个 workflow 提议了哪个 primitive？
- updater 对它执行了 ADD、UPDATE 还是 SKIP？
- consolidation 合并或拆分了什么？
- 最终 method 的证据来自哪些 gold workflows？
- 哪一步引入了 contract 变化？

## 3.9 当前 v4 gates

Candidate library 当前包含：

- gold source admission；
- provenance/source evidence；
- Python 静态解析；
- method signature 与 schema 检查；
- consolidation coverage 检查；
- workflow attribution；
- package/index 一致性检查。

当前 v4 **没有**包含：

- 每个 primitive 的实际执行测试；
- output contract runtime validation；
- consumer replay；
- update 后的 affected-task regression replay。

因此产物明确标记为：

```json
{
  "status": "candidate",
  "approved": false
}
```

presentation 主线可以聚焦 MVP，但若被问到 reliability，正确回答是：

> The current version validates provenance and structure. Behavioral contract verification is the
> next release gate.

---

## 4. Primitive retrieval 与 runtime composition

## 4.1 两阶段 retrieval

Retrieval 分成 metadata selection 与 code injection：

```text
New task
   ↓
Identify website
   ↓
Read primitive index metadata only
   ↓
Router selects USE / ADAPT / SKIP
   ↓
Only selected primitive code is loaded
   ↓
Inject complete method code
   ↓
Agent composes task-specific solution
```

为什么 retrieval 阶段不直接放完整代码：

- 减少 router prompt；
- 避免无关实现细节影响选择；
- 让选择依据是 capability、contract、requires/provides；
- 只有确定选择后才支付完整 code token cost。

为什么消费阶段必须注入完整代码：

- agent 需要实际调用或修改实现；
- 只有 signature 无法提供 selector、URL、parsing 等站点知识；
- primitive 是 synthesis material，而不只是 API 文档。

## 4.2 Router decisions

### USE

当 selected primitives 覆盖当前任务所需的完整 site-specific acquisition，剩余工作只包括薄的
task logic：

```text
primitive output
→ simple filtering/aggregation/formatting
```

### ADAPT

当 primitive 提供必要且非平凡的 acquisition，但 agent 仍需完成部分 discovery、filtering、
aggregation 或 formatting。

### SKIP

当 primitive：

- 仅关键词相关；
- 缺少必要输入；
- 只提供下游操作，没有核心 candidate set；
- 会锚定不完整策略；
- 不能实质减少当前任务的未知部分。

则不注入任何 primitive code，agent 从 scratch 求解。

## 4.3 Primitive-direct

本次 clean pilot 使用 `primitive-direct`：

```text
Task
→ metadata router
→ selected primitive code
→ agent planning and solving
```

不使用 scratch-first：

```text
Task
→ scratch plan
→ judge primitives against scratch plan
```

原因是实验希望直接测量 primitive 作为 pre-planning material 的影响，而不是同时测试 scratch
planner。

## 4.4 Copy-on-use / vendoring

Agent 使用 primitive 时，把所需代码复制或改写进新的 `final_script.py`：

```text
Active primitive package
        ↓ retrieve
Selected function code
        ↓ vendor/adapt
New standalone final_script.py
```

这带来几个重要性质：

- 历史 workflow 不依赖 active library；
- 更新 library 不会静默改变历史 workflow；
- MVP 不需要版本 pinning；
- 不需要 runtime dependency DAG；
- 不需要因 primitive 更新级联重放全部历史 workflow；
- 每个最终脚本仍可独立执行和审计。

因此当前的 hierarchy 是语义组织，而不是运行时继承图：

```text
Site package
└── Feature class
    └── Primitive method
```

---

## 5. Clean paired WebArena pilot

## 5.1 Split

Pilot 使用四个网站：

- Shopping；
- GitLab；
- Shopping Admin；
- Map。

每个网站：

- 8 个随机选择的 TRAIN templates；
- 6 个随机选择的 TEST templates；
- 每个 template 随机选择一个 task instance；
- TRAIN 与 TEST template 完全不相交；
- 选样不使用 scratch 成败、primitive overlap 或 task difficulty。

总规模：

```text
TRAIN: 4 websites × 8 templates = 32 tasks
TEST:  4 websites × 6 templates = 24 tasks
```

32 个训练任务中：

- 17 个通过 evaluator，成为 gold source；
- 建成 4 个独立 website packages；
- v4 candidate library 共包含 19 个 primitives。

按网站的 source 与 primitive 数量：

| Website | Gold source workflows | Final primitives |
|---|---:|---:|
| Shopping | 4 | 5 |
| GitLab | 7 | 8 |
| Shopping Admin | 3 | 4 |
| Map | 3 | 2 |
| **Total** | **17** | **19** |

## 5.2 Arms

### Scratch

- 不读取 workflow 或 primitive library；
- 在独立 `/tmp` experiment root 运行；
- 24 条 trajectory 扫描后，未发现 primitive retrieval、site library 或历史结果引用。

### Primitive

- metadata-first primitive router；
- `primitive-direct`；
- `use/adapt/skip`；
- 选择后完整注入 function code；
- agent 生成 standalone final script。

所有 incomplete/timeout 均保留在分母中。

## 5.3 主结果

| Method | Success | Counted agent steps |
|---|---:|---:|
| Scratch | 11/24（45.8%） | 9.58 |
| Primitive reuse | **13/24（54.2%）** | **8.50** |

可以放进 PPT 的两个大数字：

```text
+8.3 percentage points success rate
+18.2% relative improvement in solved tasks
−11.3% counted agent-execution steps
```

配对结果：

```text
3 Wins
1 Loss
10 Both correct
10 Both wrong
```

更严格的 attribution：

- task 122、154：实际注入 primitive 后的 win；
- task 113：实际注入 primitive 后的 loss；
- task 3：router `skip`，没有注入 primitive，因此视为采样波动，而非 primitive-attributable win。

### 主结果页应该强调什么

不要在主结果页用三个段落依次写“第一次污染”“没有手写”“gain concentrated”。这样的排版会让
观众首先记住实验缺陷和样本小，而不是贡献。主页面应使用三个正向 evidence blocks：

1. **Transfer to unseen templates**：24 个测试 template 均未进入 library；这是 cross-template
   transfer，不是同 template 参数替换。
2. **End-to-end automatic construction**：17 个 evaluator-admitted workflows 自动生成 19 个
   primitives，0 个 primitive 由人工编写。
3. **Joint quality improvement**：成功率提高 8.3 pp（相对多解决 18.2%），counted agent steps
   同时下降 11.3%。

Clean isolation 只放成结果表下的一行 validity badge：

> Paired clean-room evaluation · disjoint held-out templates · independently isolated scratch arm

严格 attribution 放在 speaker note 或 backup：

> Outcome-changing runs were favorable overall (3 wins / 1 loss); among runs with actual primitive
> injection, the direction remained positive (2 wins / 1 loss).

这里的意义是证明 primitive 确实产生了可归因的 positive transfer，而不是用 3 个样本声称统计显著。
“第一次运行污染”属于开发历史，不应占主结果页；如被问到 validity，再说明最终数字来自重新运行的
clean-room scratch baseline，且 24 条 trajectory 均完成 artifact-access audit。

## 5.4 按网站结果

| Website | Scratch | Primitive |
|---|---:|---:|
| Shopping | 4/6 | 4/6 |
| GitLab | 2/6 | 2/6 |
| Shopping Admin | 4/6 | 5/6 |
| Map | 1/6 | 2/6 |
| **Total** | **11/24** | **13/24** |

## 5.5 Step metric 如何描述

可以报告：

> Counted agent-execution steps decrease from 9.58 to 8.50, an 11.3% reduction.

必须在页脚注明：

> Steps exclude offline library construction and retrieval/routing overhead.

原因：当前 Webwright step counter 从 downstream agent 开始计数，不包含 primitive metadata retrieval、
router LLM call 和 frozen-plan preparation。

另外，在双方都正确的 10 个任务中：

- Scratch：7.6 steps；
- Primitive：8.0 steps。

因此不能声称 primitive 已证明端到端效率更高。主 presentation 可以只展示总体 counted agent steps；
如果被追问，则说明该指标反映 downstream execution length，而不是 total token/wall-clock cost。

## 5.6 最安全的结果表述

推荐：

> On a clean paired 24-task WebArena pilot, site-scoped primitive reuse improves success from
> 45.8% to 54.2% (+8.3 percentage points).

如果同时展示 steps：

> Primitive reuse improves success by 8.3 percentage points while reducing counted agent-execution
> steps by 11.3%.

不要声称：

- statistically significant；
- overall WebArena state-of-the-art；
- end-to-end cost 下降 11.3%；
- 所有网站或 primitive 类型都稳定提升；
- v4 已经是 release-grade verified library。

---

## 6. Workflow 与 primitive 的直接比较

在后续 59-task scale-up 中，完整 cross-template workflow adaptation 与 primitive adaptation 的直接
结果是：

| Cross-template material | Success |
|---|---:|
| Complete workflow adaptation | 33/59（55.9%） |
| Primitive-v4-direct | 37/59（62.7%） |

配对 primitive 相对 workflow：

- 9 win；
- 5 loss；
- 28 both-correct；
- 17 both-wrong；
- net +4；
- accuracy +6.8 percentage points。

它支持 granularity 的核心论点：

> Fine-grained site primitives transfer better across templates than complete workflow priors.

如果 presentation 时间很短，可以只在 workflow → primitive 的 transition slide 放一句：

> Primitive-level transfer outperforms complete workflow adaptation by 6.8 percentage points.

---

## 7. Scale-up 与 Map debug（Backup slide）

这一部分不建议放在主结果页，但应该准备在 Q&A 或 backup 中。

## 7.1 Scale-up protocol

- 正式 TRAIN：120 tasks；
- gold sources：66；
- T2：59 instances / 33 全新 templates；
- scratch、workflow、primitive 三臂严格隔离；
- evaluator/runtime/model 冻结；
- primitive 使用 v4 direct router，不使用 scratch-first。

## 7.2 Scale-up result

| Arm | Accuracy | Mean steps |
|---|---:|---:|
| Scratch | 43/59（72.9%） | 15.15 |
| Workflow-adapt | 33/59（55.9%） | 13.68 |
| Primitive-v4-direct | 37/59（62.7%） | 11.44 |

Primitive 没有打赢 scratch，但 regression 高度集中在 Map：

| Website | Scratch | Primitive |
|---|---:|---:|
| GitLab | 7/9 | 7/9 |
| Shopping | 10/15 | 11/15 |
| Shopping Admin | 12/16 | 12/16 |
| Map | 14/19 | 7/19 |

排除正在 debug 的 Map：

| Metric | Scratch | Primitive |
|---|---:|---:|
| Accuracy | 29/40（72.5%） | 30/40（75.0%） |
| Mean steps | 14.05 | 12.23 |

即非 Map 子集：

- accuracy +2.5 percentage points；
- counted steps −13.0%。

这是 post-hoc diagnostic subset，不应代替正式总体结果。

## 7.3 Map 已定位的问题

### Coupled routing configuration

Map deployment 用 endpoint/port 区分交通模式，但 primitive 将 `profile` 与 `base_url` 暴露成两个
独立参数。Consumer 可以构造：

```text
walking profile + driving/default endpoint
```

返回 JSON 结构合法，但 route step 实际仍是 driving。这种错误无法被静态 schema gate 捕获。

### Incomplete candidate acquisition

`search_places` 返回 ranked top-k，并声明：

```json
{"is_complete": false}
```

Router 却在 exact-set、附近所有对象和 NOT_FOUND-sensitive task 上选择 `adapt`。非完整候选不能
证明“所有结果”或“不存在结果”。

### 下一版修复

```text
get_route(transport_mode)
→ primitive 内部绑定正确 endpoint/profile
→ runtime invariant validates returned mode

candidate acquisition metadata
→ complete / exhaustive / scope
→ exact-set task lacks core candidate set => SKIP
```

这个发现对应 release pipeline 的下一层：

```text
Candidate primitive
→ executable contract tests
→ semantic invariants
→ affected-consumer regression tests
→ approved primitive
```

---

## 8. 推荐 PPT 结构

下面是一套 6 页主 deck，加 2 页 backup。

## Slide 1 — Problem

### Title

**From Workflow Reuse to Cross-template Site Primitives**

### Main visual

```text
Same template
Task A(x) ───────────────→ Workflow A(params)

Cross template, same website
Task A + Task B + Task C → Shared site operations
```

### Bullets

- Complete workflows are effective for same-template reuse.
- Cross-template tasks share website operations but differ in task strategy.
- Reusing the whole workflow transfers too much task-specific logic.

### Speaker note

> Web Skill Factory originally stores successful tasks as complete parameterized workflows. This is
> natural when the new task follows the same template. For cross-template tasks on the same website,
> only part of the workflow is reusable, such as login, project lookup, pagination, or stable parsing.

## Slide 2 — Workflow-level Web Skill Factory

### Title

**Workflow-level Reuse**

### Diagram

```text
Successful executions
→ group by template
→ parameterize instances
→ standalone workflow skill
→ retrieve
→ USE / ADAPT / SKIP
```

### Right-side limitation

```text
Reusable site operation
+ source-specific filtering
+ source-specific aggregation
+ source-specific output schema
= complete workflow prior
```

### Bottom line

> Cross-template workflow adaptation is too coarse-grained.

## Slide 3 — Primitive Factory

### Title

**Building a Site Primitive Package**

### Diagram

```text
Gold workflows from one website
        ↓
Per-workflow extraction
        ↓
Batch update: ADD / UPDATE / SKIP
        ↓
Consolidate: MERGE / SPLIT / ORGANIZE
        ↓
Object-oriented site package
```

### Package visual

```text
GitLabSite
├── Auth
├── Projects
└── Commits
    └── list_repository_commits(...)
```

### Bottom line

> Granularity is determined by reusable operations shared across templates.

## Slide 4 — Retrieval and Composition

### Title

**Metadata-first Retrieval, Full-code Composition**

### Diagram

```text
New task
→ retrieve metadata
→ USE / ADAPT / SKIP
→ inject selected full function code
→ agent composes task logic
→ standalone final script
```

### Three implementation decisions

- Metadata-only selection keeps retrieval compact.
- Complete code is injected only after selection.
- Copy-on-use avoids runtime dependencies and version pinning.

### Bottom line

> Primitives are synthesis material, not runtime dependencies.

## Slide 5 — Evaluation

### Title

**Clean Cross-template WebArena Evaluation**

### Protocol

```text
4 websites
32 train templates
24 disjoint held-out templates
17 evaluator-admitted source workflows
19 automatically generated primitives
```

### Arms

```text
Scratch vs Primitive-direct
```

### Footer

> No primitive was manually written; scratch trajectories were isolated and audited.

## Slide 6 — Result

### Title

**Automatically Generated Primitives Transfer to Unseen Templates**

### Table

| Method | Success | Agent steps |
|---|---:|---:|
| Scratch | 45.8% | 9.58 |
| Primitive reuse | **54.2%** | **8.50** |
| Delta | **+8.3 pp** | **−11.3%** |

### Hero statement

```text
18.2% more held-out tasks solved
with 11.3% fewer counted agent steps
```

### Three evidence blocks

```text
UNSEEN-TEMPLATE TRANSFER
All 24 test templates were disjoint from library construction.

FULLY AUTOMATIC LIBRARY
17 gold workflows → 19 primitives; 0 handwritten primitives.

CONSISTENT SITE-LEVEL DIRECTION
Improved on 2/4 websites and maintained accuracy on the other 2.
```

### Bottom line

> The factory converts successful workflows into reusable website operations that improve new task
> templates without manually engineering the library.

### Footer

> Clean paired retrieval-only pilot · 4 websites · disjoint held-out templates · gpt-5.4. Steps
> exclude offline build and routing overhead.

### Speaker note / optional small-print attribution

> Paired outcomes were 3 wins and 1 loss. Restricting attribution to runs with actual primitive
> injection gives 2 wins and 1 loss. This is a development pilot, not a significance claim.

## Backup 1 — Workflow vs Primitive

```text
Complete workflow adaptation: 33/59
Primitive adaptation:         37/59

+6.8 percentage points
```

## Backup 2 — Reliability and Next Step

```text
Candidate package
→ provenance + static validation      [implemented]
→ executable contract tests           [next]
→ affected-consumer regression tests  [next]
→ release package
```

## Backup 3 — Evaluation Validity

```text
Template isolation
Train and test templates are disjoint.

Arm isolation
Scratch ran in an independent clean experiment root.

Artifact audit
24/24 scratch trajectories contained no primitive-library or cross-arm references.

Paired accounting
Timeouts remain in the denominator; all tasks use the same evaluator and model family.
```

---

## 9. 讲稿压缩版

## 30 秒版本

> Web Skill Factory originally reuses complete parameterized workflows, which works naturally for
> tasks from the same template. For cross-template tasks on the same website, complete workflows are
> too coarse because they mix reusable site operations with task-specific reasoning. I implemented a
> site primitive factory that extracts operations from evaluator-passing workflows, incrementally
> updates them with ADD, UPDATE, and SKIP, and then merges, splits, and organizes them into an
> object-oriented site package. At runtime, the system retrieves metadata, decides use, adapt, or
> skip, and injects only the selected full function code. On a clean paired 24-task WebArena pilot,
> success improved from 45.8% to 54.2%.

## 90 秒版本

> The original Web Skill Factory stores a successful task as a complete standalone workflow. By
> comparing instances from the same template, it parameterizes values and reuses the workflow for
> future tasks. However, when the new task belongs to a different template, only some operations are
> shared. Injecting the whole workflow also transfers source-specific filtering, aggregation, and
> output decisions.
>
> I therefore introduced a second reuse unit: a site-scoped primitive. Gold workflows from the same
> website are processed in deterministic batches. For each batch, the updater can add a new
> primitive, update an existing one, or skip task-specific logic. A final consolidation stage merges
> duplicates, splits mixed responsibilities, and organizes methods into feature classes such as Auth,
> Orders, Reviews, Projects, and Commits. Every method has an input/output contract and source
> provenance.
>
> During consumption, the router first sees only metadata and decides use, adapt, or skip. Only then
> is complete selected code injected. The code is copied into a new standalone workflow, so there is
> no runtime dependency on the evolving library. In a clean paired WebArena pilot across four
> websites, primitive reuse improved success from 11 out of 24 to 13 out of 24, or 8.3 percentage
> points.

---

## 10. 常见 Q&A

### Q1. 为什么不用完整 workflow？

> A complete workflow contains both reusable website operations and source-task strategy. Across
> templates, that strategy can be irrelevant or actively misleading. Primitive retrieval exposes a
> smaller reusable unit.

### Q2. Primitive 是手写的吗？

> No. All primitives are generated by the pipeline from evaluator-admitted gold workflows. The
> 24-task pilot library used 17 admitted workflows and produced 19 primitives.

### Q3. 为什么要 batch，而不是一次输入所有 workflows？

> Primitive granularity requires cross-template comparison, but an entire website may contain dozens
> or hundreds of workflows. Deterministic batches keep prompts bounded, while the shared primitive
> pool preserves cross-batch accumulation. A final site-wide consolidation removes order-dependent
> duplication.

### Q4. ADD / UPDATE / SKIP 与 MERGE / SPLIT 的区别？

> ADD, UPDATE, and SKIP are cheap incremental decisions made as workflows arrive. MERGE, SPLIT, and
> ORGANIZE are site-level normalization operations performed after the complete update pass.

### Q5. 为什么每个网站一个 package？

> Selectors, APIs, authentication, URL structure, and parsing conventions are website-specific. A
> site package is therefore the natural sharing boundary for cross-template reuse.

### Q6. 为什么 object-oriented？

> The root site object provides one stable namespace, while feature classes such as Orders or Commits
> keep the library navigable as it grows. The classes organize capability; they do not create a deep
> runtime inheritance hierarchy.

### Q7. Primitive 会不会导致依赖和版本混乱？

> The MVP uses copy-on-use. Selected code is vendored into a standalone final script. Historical
> workflows do not import the active primitive package, so package updates do not silently change
> past workflows and do not require dependency pinning.

### Q8. Primitive 是否经过验证？

> The candidate pipeline verifies evaluator-admitted provenance, syntax, contracts, attribution, and
> consolidation coverage. Executable behavioral contract tests are the next release gate, so the
> current package is explicitly marked candidate rather than approved.

### Q9. 24 个任务是否足够？

> It is a clean paired development pilot rather than a statistical significance claim. Its purpose is
> to validate that automatically generated primitives can produce cross-template behavioral gains.
> The larger evaluation is used for diagnosing contract and routing failures before release.

### Q10. 11/24 → 13/24 中有多少是真正由 primitive 带来的？

> The paired arm result is three wins and one loss. Two wins and the one loss occurred with actual
> primitive exposure. One additional win was routed to skip and is treated as sampling variation.

### Q11. Steps 为什么可以下降？

> The reported number counts downstream agent-execution steps. It decreases from 9.58 to 8.50, but it
> excludes the router call and offline build, so it is not presented as an end-to-end cost claim.

### Q12. 下一步是什么？

> Add executable contract tests, candidate-set completeness metadata, and affected-consumer
> regression tests; then promote only behaviorally validated primitives from candidate to release.

---

## 11. 可以安全使用的数字

### 主结果

```text
Scratch:   11/24 = 45.8%
Primitive: 13/24 = 54.2%
Delta:     +8.3 percentage points
```

### Agent steps

```text
Scratch:   9.58
Primitive: 8.50
Delta:     −11.3%
```

脚注：

```text
Counted agent-execution steps; offline library construction and routing overhead excluded.
```

### Primitive vs workflow

```text
Workflow adaptation: 33/59 = 55.9%
Primitive:           37/59 = 62.7%
Delta:               +6.8 percentage points
```

### 非 Map scale-up diagnostic

```text
Scratch:   29/40 = 72.5%, 14.05 steps
Primitive: 30/40 = 75.0%, 12.23 steps
Delta:     +2.5 pp, −13.0% steps
```

必须标记为：

```text
Post-hoc diagnostic subset; Map contract under debugging.
```

---

## 12. 实现与结果路径

### Pipeline implementation

- Workflow evolution：`src/webwright/skill_factory/update.py`
- Audited primitive build：`src/webwright/skill_factory/audited_primitive_build.py`
- Audited primitive retrieval：`src/webwright/skill_factory/audited_primitive_retrieve.py`
- Direct WebArena routing/eval：`evals/webarena/cross_task_eval.py`
- Reuse experiment runner：`evals/webarena/run_reuse_experiment.py`
- Result summarizer：`evals/webarena/summarize_reuse_eval.py`

### 24-task pilot

- Library：`evals/webarena/site_libraries_32_24_audited_20260810_v4/`
- Results：`evals/webarena/formal_32_24_audited_v4_clean_results/`
- Summary：`evals/webarena/formal_32_24_audited_v4_clean_results/summary.json`

### Scale-up experiment

- Split：`evals/webarena/reuse_split_v1.json`
- Primitive library：`evals/webarena/reuse_split_v1_primitive_library_v4/`
- Compact results：`evals/webarena/reuse_split_v1_eval_results/`
- Chinese analysis：`evals/webarena/reuse_split_v1_report_zh.md`
- Human review items：`evals/webarena/review_required.md`

### Frozen implementation references

- Workflow parameter-extension implementation：commit `590beeab9b539cf938466e56128c4e5695a469ef`
- Audited primitive-v4 implementation：commit `14b8adb`
- Completed scale-up artifacts and report：commit `5ee290dcc37e18789e30b2bb3e4125d055c56563`

---

## 13. 最终可直接复制到 conclusion slide 的内容

### Title

**Conclusion**

### Bullets

- Extended Web Skill Factory from complete workflows to site-scoped primitives.
- Implemented auditable extraction, incremental update, consolidation, and object-oriented package
  organization.
- Added metadata-first `use/adapt/skip` retrieval with full-code copy-on-use composition.
- Improved clean paired WebArena success from **45.8% to 54.2%**.
- Identified executable behavioral contract validation as the next release gate.

### Closing sentence

> The key lesson is that cross-template reuse needs a finer unit than a complete workflow: reusable
> website operations with explicit contracts, provenance, and controlled composition.

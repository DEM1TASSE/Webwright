# Cross-Task Primitive MVP：实现与评测计划

> **当前建议的实现规格。** 本文收敛此前关于 hierarchy、DAG、shared imports 和 replay
> 的讨论。MVP 只回答一个问题：从同网站、不同 task templates 的正确完整程序中提取
> primitive，并在新模板上检索这些代码，能否帮助 agent 生成更好的完整 workflow？
>
> MVP 中 primitive **不是独立 executable package**。它是 gold-grounded synthesis
> material。完整的 executable、gate、dependency 和 replay 设计见
> [`cross_task_primitive_release.md`](cross_task_primitive_release.md)。
>
> 本文优先级高于此前的 brainstorming 文档。此前文档中关于 public DAG、workflow
> runtime import、primitive version pinning 和全量 dependent replay 的内容均不属于 MVP。

## 1. 核心决定

### 1.1 Workflow 仍是完整代码

一个 workflow 对应一个 task template。同模板的不同 task instances 继续通过当前的
参数化和 pattern 泛化合并：

```text
same template, different instances
→ parameterized standalone workflow
```

每个 workflow 保存完整、自包含、可独立执行的 `skill.py`：

```text
library/
└── <workflow_id>/
    ├── skill.py
    ├── meta.json
    └── replays.json
```

即使 workflow 使用了 retrieved primitive，它最终也必须把所需实现包含在自己的
`skill.py` 中，不在运行时 import primitive catalog。

### 1.2 Primitive 是 synthesis material

Primitive 的定义：

> A site-scoped, retrievable code unit distilled from multiple gold-admitted task
> workflows and used as synthesis material for producing a new standalone workflow.

Primitive：

- 绑定一个网站；
- 有名称、capability、signature 和代码；
- 来源于至少两个不同 task templates，或由人工/oracle 标注进入实验；
- 在新任务 solve 前被检索并提供给 agent；
- 不作为历史 workflow 的 runtime dependency；
- 更新后不会改变已有 workflow。

#### Active catalog 自包含不变量

> Active catalog 中任意两个 primitive 文件互不引用；每个注入给 agent 的 primitive
> snippet 必须独立可解析。所需 private helpers 内联在同一文件中，允许跨文件重复。

`requires/provides` 只表示浏览器环境状态，不表示代码 import 或函数调用。例如
`open_repo` 要求 `authenticated_session`，workflow 仍需显式安排
`login(); open_repo(repo)`。

### 1.3 Canonical state 只有两个集合

```text
Workflow Library
  完整、独立、template-level programs

Primitive Catalog
  当前 active、site-scoped、供生成时复用的 code units
```

两者之间只有 provenance，不存在运行时依赖：

```text
Primitive Catalog
       ↓ retrieve / copy / adapt at solve time
Standalone Workflow
```

### 1.4 MVP 不实现

- public primitive DAG；
- intermediate workflow hierarchy；
- primitive runtime imports；
- workflow lockfile；
- primitive semantic versions；
- dependent workflow migration；
- primitive 更新后的全库 replay；
- 持久化 recipe 层；
- 通用自动 planner；
- 自动 package dependency solver。

## 2. 为什么采用完整 Workflow

如果 workflow runtime import shared primitive：

```text
primitive update
→ many workflows affected
→ version pinning
→ migration
→ large regression surface
```

MVP 使用 copy-on-use / vendoring：

```text
retrieve primitive code
→ agent creates a complete final script
→ final script is stored independently
```

这会重复少量源码，但避免：

- library evolution 隐式破坏历史 workflow；
- primitive 版本和依赖管理；
- replay 时间随整个 library 线性增长；
- cross-task 实验被包管理工程淹没。

MVP 的目标是减少 agent 重新探索网站的成本，而不是最小化磁盘上的代码重复。

## 3. 数据布局

建议在 library 下使用隐藏目录，避免被当前 workflow `Library.list()` 当成普通 skill：

```text
library/
├── .primitives/
│   ├── gitlab/
│   │   ├── catalog.json
│   │   └── code/
│   │       ├── open_repo.py
│   │       └── get_project_commits.py
│   └── shopping_admin/
│       ├── catalog.json
│       └── code/
│           ├── get_product_reviews.py
│           └── update_product_description.py
│
├── commits_by_user_date/
│   ├── skill.py
│   ├── meta.json
│   └── replays.json
└── reviews_below_rating/
    ├── skill.py
    ├── meta.json
    └── replays.json
```

### 3.1 Primitive metadata

```json
{
  "primitive_id": "shopping_admin/get_product_reviews",
  "site": "shopping_admin",
  "status": "active",
  "capability": "Retrieve normalized reviews for a product.",
  "signature": {
    "inputs": {
      "product": "string",
      "taskspec": "object"
    },
    "output_schema": {
      "type": "array",
      "items": {"$ref": "Review"}
    }
  },
  "requires": ["authenticated_session"],
  "provides": ["review_records"],
  "source_templates": [249, 250, 288],
  "source_workflows": [
    "reviews_below_rating",
    "reviews_above_rating",
    "count_keyword_reviews"
  ],
  "supported_patterns": [
    "product_edit_entry",
    "review_grid_entry"
  ],
  "code_path": "code/get_product_reviews.py",
  "content_hash": "sha256:...",
  "created_from": ["run-id-1", "run-id-2"]
}
```

`content_hash` 仅用于 provenance、实验复现和 cache invalidation，不参与版本求解。

### 3.2 Workflow provenance

Workflow 可以记录它生成时拿到了哪些 primitive：

```json
{
  "workflow_id": "update_description_from_reviews",
  "site": "shopping_admin",
  "template": "...",
  "primitive_sources": [
    {
      "primitive_id": "shopping_admin/get_product_reviews",
      "content_hash": "sha256:..."
    }
  ]
}
```

这不是 dependency；primitive 后续更新不会影响 workflow。

## 4. Pipeline 变化

当前主流程：

```text
solve
→ correctness gate
→ same-template grouping
→ distill/update complete workflow
→ library
```

MVP 增加两个旁路组件：

```text
                               ┌→ Primitive Updater → Primitive Catalog
gold-admitted workflows/runs ──┤
                               └→ Existing Workflow Learn/Update

new task
→ Workflow Retrieve
→ if no exact workflow: Primitive Retrieve
→ agent solve with primitive code
→ complete standalone workflow
```

Primitive updater 不阻塞现有 workflow learn。即使 primitive extraction 失败，完整 workflow
仍然可以正常写入 library。

### 4.1 新 Task 以什么为基础

生产系统最终仍保留原规则：

> 有 same-template workflow 时，以 workflow 为基础；没有时才使用 primitives。

```text
new task
├── same-template workflow exists
│   ├── covered instance → RUN_WORKFLOW
│   └── new parameter/pattern → ADAPT_WORKFLOW
│
└── no same-template workflow
    ├── relevant primitives → COMPOSE_PRIMITIVES
    └── no relevant primitive → SCRATCH
```

Primitive 不替代已有 workflow，因为 workflow 已包含 task intent、参数、filter、aggregation
和最终输出。

但本轮 **cross-template MVP evaluation 不测试上述 same-template 分支**。所有 held-out
task 的 template 必须与 workflow/primitive source templates 不相交。实验状态机只比较：

```text
new held-out task
→ retrieve metadata for workflows from OTHER templates
   ├── ADAPT_WORKFLOW
   └── SKIP_WORKFLOW
          ↓
   retrieve generated primitive metadata
   ├── USE_PRIMITIVE
   ├── ADAPT_PRIMITIVE
   └── SKIP_PRIMITIVE → SCRATCH
```

`USE_WORKFLOW`（same-template 参数实例化）留在原 pipeline 中，但不进入本轮 split、指标
或结论。MVP 也暂时不同时注入 workflow 与 primitive：workflow 选择 adapt 后就停止；
只有 workflow skip 才进入 primitive 分支。

运行时不能使用 WebArena 的 `intent_template_id` 判定匹配；它只用于实验 split。匹配依据
是 task intent、参数槽、output schema、task type 和 site。

### 4.2 成功后更新什么

```text
successful solve
├── template 已存在
│   → UPDATE_WORKFLOW
│     参数、pattern 或 task-level logic 继续按当前机制泛化
│
└── 新 template
    → ADD_WORKFLOW
      保存完整 standalone code
```

随后 Primitive Updater 异步比较同网站、不同 templates 的 workflows：

```text
same-site cross-template comparison
→ ADD / MODIFY / SPLIT / ARCHIVE / NO_CHANGE primitive proposal
```

因此：

```text
same-template evidence → workflow update
cross-template evidence → primitive update
```

即使新 task 使用了 primitive，也先保存正确的完整 workflow；它不会直接修改 primitive。
Primitive 更新失败同样不阻塞 workflow 入库。

## 5. Primitive Updater

### 5.1 触发时机

不是每个 task instance 都触发 primitive update。

```text
same template new instance
→ only update workflow

new template obtains first gold-admitted workflow
→ compare across same-site workflows
→ propose primitive catalog update
```

这样 primitive evolution 的频率与新 templates 数量相关，而不是与所有 runs 数量相关。

### 5.2 输入

```text
- 新 gold-admitted workflow 的完整代码
- 同网站已有 workflow 代码与 metadata
- 当前 active primitive catalog
- task templates、parameters、output schemas
- source trajectories（如果可用）
```

### 5.3 更新操作

MVP 支持：

```text
ADD
MODIFY
SPLIT
ARCHIVE
NO_CHANGE
```

#### ADD

不同 templates 重复实现新的、可命名的网站能力：

```text
reviews_below_rating
+ count_keyword_reviews
→ ADD get_product_reviews
```

默认 promotion gate：

```text
source_template_count >= 2
+ website-semantic capability
+ clear inputs/output
+ source workflows gold-admitted
+ candidate smoke checks pass
```

#### MODIFY

新 workflow 暴露出同一 capability 的更稳健实现或新页面 pattern：

```text
existing get_product_reviews
+ new entry path / selector / pagination evidence
→ replace active catalog implementation
```

已有 workflows 不受影响，因为它们保存完整代码。

候选失败时保留旧 active primitive。

#### SPLIT

已有 primitive 太粗，新 templates 只共享其中一部分：

```text
A = B + C
new workflow needs C
→ replace active retrieval surface A with canonical B and C
```

旧 A 可以移入 `.archive/`，或只留在 Git 历史。使用过 A 的历史 workflows 无需迁移。

MVP 避免让 A、B、C 同时出现在 active retrieval surface，减少重叠粒度造成的选择歧义。

#### ARCHIVE

以下 primitive 退出 active retrieval：

- 被 SPLIT 或更好实现替代；
- capability 与其他 primitive 重复；
- 没有跨模板证据；
- 多次被检索但从未实际帮助；
- 代码或 contract 已知无效。

Archive 不影响历史 workflows。

### 5.4 Updater 输出格式

LLM 不直接写 catalog，而是先输出结构化 proposal：

```json
{
  "operations": [
    {
      "op": "ADD",
      "primitive_id": "shopping_admin/get_product_reviews",
      "capability": "Retrieve normalized reviews for a product.",
      "source_templates": [249, 288],
      "reason": "Both workflows repeat product lookup, review navigation, pagination, and extraction.",
      "candidate_code": "..."
    }
  ]
}
```

系统检查 proposal 后才落盘。

### 5.5 Candidate checks

MVP 不对 primitive 做独立网页行为 gate，也不声称 primitive standalone executable 或
replay-verified。最低 admission checks 只有：

1. 来源 workflows 已通过 benchmark/gold evaluator；
2. candidate 能被 AST parse 和 Python compile；
3. metadata signature 与代码入口一致；
4. candidate 不引用未一并注入的其他 catalog primitive；
5. private helpers 已内联，snippet 可以独立解析；
6. 代码不硬编码 source task 的最终答案；
7. capability/signature 与来源 workflows 基本一致；
8. MODIFY/SPLIT proposal 未通过上述检查时保留旧 catalog。

Primitive 的行为价值在 oracle-use 和 end-to-end WebArena evaluation 中证明。更强的行为
gate 属于 release 阶段。

## 6. Primitive Retriever

### 6.1 Routing

```text
1. Detect site
2. Retrieve metadata for workflows from other templates
3. Metadata-only workflow decision:
   - adapt: inject one complete workflow as cross-template prior
   - skip: continue
4. Retrieve generated primitive metadata only
5. Metadata-only primitive decision:
   - use/adapt: then fetch and inject selected full primitive code
   - skip: scratch; full primitive code never enters the prompt
```

为保证 cross-template 实验归因清楚，MVP 暂时不混合 `adapt_workflow` 与 primitive
injection，也不测试 same-template workflow use：

```text
cross-template workflow adapt
or
generated primitive use/adapt
or
scratch
```

Benchmark 的 `intent_template_id` 只用于 split 和评估，不能作为 runtime routing 输入。

Router 不实现 budget model。它只使用简短规则：

```text
USE    contract directly supplies the core website facts
ADAPT  material covers a meaningful part, with explicit remaining gaps
SKIP   prerequisites are the main unresolved work, output is unnecessary, or coverage is marginal
```

决定 use/adapt/skip 时只能看 metadata。完整代码在 use/adapt 之后才读取，以免
`SKIP` 决定本身已经受到代码 anchoring。

### 6.2 Capability decomposition

Retriever 先把 task 分成：

```text
- website capabilities
- task-specific logic
```

例如：

```text
Task:
  根据四星及以上评论数量更新产品描述

Website capabilities:
  - retrieve product reviews
  - update product description

Task-specific logic:
  - filter rating >= 4
  - count
  - construct description string
```

### 6.3 Candidate filtering and ranking

Hard filters：

```text
site matches
status is active
declared inputs can be supplied or inferred
```

Ranking signals：

```text
capability semantic match
+ output schema usefulness
+ requires/provides compatibility
+ source template diversity
+ prior held-out utility
- injected code/token cost
```

MVP 每个网站 primitive 数量较少时，可以直接把该网站全部 metadata 交给 decision LLM。
规模增长后再增加 embedding prefilter。

### 6.4 Preconditions

`requires/provides` 只表示环境状态，不表示 primitive 代码依赖：

```yaml
login:
  requires: []
  provides: [authenticated_session]

open_repo:
  requires: [authenticated_session]
  provides: [repo_context]
```

Retriever 对 selected primitives 做一轮缺口检查：

```text
selected open_repo
→ missing authenticated_session
→ suggest login
```

不实现任意图规划。

### 6.5 Retriever 输出

```json
{
  "mode": "compose_primitives",
  "selected": [
    "shopping_admin/get_product_reviews",
    "shopping_admin/update_product_description"
  ],
  "suggested_order": [
    "get_product_reviews",
    "<task-specific filtering/count>",
    "update_product_description"
  ],
  "missing_logic": [
    "filter reviews with rating >= 4",
    "construct description"
  ]
}
```

MVP 最多注入 3–5 个 primitives，避免把整个 site catalog 作为上下文。

## 7. Agent Use

Agent 收到：

- primitive ID；
- capability 和 signature；
- requires/provides；
- 完整 primitive code；
- suggested order；
- 明确列出的 missing task logic。

Prompt 约束：

```text
Use the supplied website primitives where applicable.
Write task-specific filtering, aggregation, formatting, and mutation decisions yourself.
The final script must be standalone: copy or adapt any needed primitive implementation into
the final script. Do not import the primitive catalog at runtime.
```

最终 `skill.py` 是完整代码。

### 7.1 Usage instrumentation

只靠模型自报“使用了 primitive”不可靠。MVP 同时记录：

1. agent 声明的 `primitive_usage.json`；
2. final script 中保留的来源标记：

   ```python
   # Derived from primitive: shopping_admin/get_product_reviews
   ```

3. AST/function similarity 或代码片段匹配；
4. primitive capability 对应的调用是否真的出现在执行路径中。

实验报告区分：

```text
retrieved
declared-used
code-incorporated
execution-reached
```

## 8. 元能力如何测试

不能只测最终 WebArena accuracy，否则无法判断失败来自 updater、retriever、agent use 还是
primitive 本身。测试拆为四层。

### 8.1 Updater Unit Evaluation

构建一组小型、人工标注的 workflow triples：

```text
Case ADD:
  W1/W2 共享评论抽取 → 应 ADD get_product_reviews

Case MODIFY:
  新 workflow 增加分页 pattern → 应 MODIFY get_product_reviews

Case SPLIT:
  A=B+C，新 workflow 只复用 C → 应 SPLIT A

Case NO_CHANGE:
  同网站但页面责任无关 → 不应抽象
```

指标：

```text
operation accuracy
primitive boundary precision/recall
signature/schema correctness
compile rate
hardcoded-answer rejection rate
false abstraction rate on negative pairs
```

第一版可以用 20–40 个人工 cases，不需要大规模 benchmark。

### 8.2 Retriever Evaluation

为选定的 WebArena held-out templates 人工标注 oracle primitives：

```json
{
  "task_template": 251,
  "oracle_primitives": [
    "shopping_admin/get_product_reviews",
    "shopping_admin/update_product_description"
  ]
}
```

指标：

```text
Recall@1 / @3 / @5
Precision@k
exact set match
irrelevant code tokens injected
requires gap detection accuracy
```

增加 negative tasks：同网站但没有可复用 primitive，测 correct empty retrieval。

### 8.3 Agent Use Evaluation

固定正确的 oracle primitives，绕过 retrieval，测试 agent 是否能实际使用：

```text
Scratch
vs
Oracle primitive metadata only
vs
Oracle primitive code
```

指标：

```text
task success
primitive incorporation rate
execution-reached rate
steps/tokens/wall time
newly written website code ratio
```

如果 oracle code 都无收益，就不应继续优化 retrieval。

### 8.4 End-to-End Cross-Template Evaluation

严格按 `intent_template_id` 隔离：

```text
Train:
  same website, selected templates

Test:
  unseen templates from the same website
```

建议第一组：

```text
Shopping Admin train:
  249  reviews <= 3 stars
  250  reviews >= 4 stars
  288  count reviews containing keyword

Shopping Admin test:
  244  most unhappy customer information
  251  update product description from high-rating count
```

Baselines：

1. Scratch；
2. Cross-template workflow adapt（只允许 source template）；
3. Forced oracle generated primitives（绕过 router，测正负影响）；
4. Metadata-routed generated primitives（use/adapt/skip）；
5. Full routed system（workflow adapt/skip → primitive use/adapt/skip → scratch）；
6. 如果实现成本允许，SkillLens-style textual procedural units。

不包含 same-template workflow arm。所有 primitive 必须由 updater 从 gold-admitted、
未消费 primitive 的 source workflows 自动生成；手写/oracle primitive catalog 不进入本轮
效果数字。Oracle 只指定 generated primitive ID，不提供人工实现。

主要指标：

```text
WebArena evaluator success
agent steps
token cost
wall time
primitive retrieval precision/recall
primitive execution-reached
catalog size
```

### 8.5 Chronological Evolution Test

按模板顺序逐个加入：

```text
empty catalog
→ template A
→ template B
→ template C
→ held-out D
```

每一步记录：

```text
ADD/MODIFY/SPLIT/ARCHIVE operations
active primitive count
duplicate/overlap rate
update acceptance rate
retrieval utility on fixed validation templates
```

这直接测试“library 越用越大时是否失控”。

### 8.6 Growth Controls

MVP 设置：

```text
promotion requires >= 2 source templates
maximum active primitives per site: configurable, initially 20–30
maximum injected primitives per task: 3–5
archive primitives with repeated zero utility
keep all provenance in logs, but only active catalog participates in retrieval
```

需要报告 catalog growth curve，而不是只报告最终 accuracy。

### 8.7 WebArena 两套 ID

新实验必须区分：

```text
intent_template_id:
  数据集模板 ID，例如 249

task_id:
  具体实例 ID，例如 213、214、215、216、217

representative_task_id:
  旧 reproduce.py 用作 SPLITS key 的代表任务 ID，例如 213
```

新 split 文件必须同时保存：

```yaml
intent_template_id: 249
intent_template: "Get the title and rating ..."
representative_task_id: 213
train_task_ids: [213, 214, 215]
heldout_task_ids: [216, 217]
```

加载时必须验证每个 `task_id` 在数据集中的 `intent_template_id` 等于声明值，不一致立即
失败，避免模板 ID 和代表 task ID 静默错位。

### 8.8 已知限制：False Abstraction

MVP 的静态 checks 无法完全阻止“表面相似但语义不应合并”的 primitive。Vendoring 使
误抽象不会破坏历史 workflows，但仍会造成 catalog 膨胀、retrieval 噪声和无用代码注入。

MVP 通过以下措施限制而非消灭风险：

```text
至少两个不同 source templates
NO_CHANGE / negative updater cases
active catalog size cap
retrieved-but-unused 统计
重复/重叠 primitive 统计
长期零 utility primitive archive
```

必须报告 false abstraction rate、catalog growth、overlap/duplicate rate 和
retrieved-but-unused rate。更强的行为 gate 属于 release。

## 9. 实现位置

基于当前模块，建议最小改动如下。

### 新模块

```text
src/webwright/skill_factory/primitive_catalog.py
  load/list/add/replace/archive primitives

src/webwright/skill_factory/primitive_update.py
  compare cross-template workflows
  propose ADD/MODIFY/SPLIT/ARCHIVE
  validate and apply proposal

src/webwright/skill_factory/primitive_retrieve.py
  capability decomposition
  site-scoped selection
  requires/provides gap check
```

### 修改模块

```text
learn.py / update.py
  workflow 成功落库后，可选触发 primitive updater

route.py
  exact workflow 失败后进入 primitive retrieval

prompt.py
  构造 primitive-aware agent prior

library.py
  workflow 行为保持不变；primitive catalog 由独立类管理
```

### CLI

第一版把新能力放在显式 experimental flags 后：

```bash
python -m webwright.skill_factory learn runs/ \
  --library ./library \
  --update-primitives
```

```bash
python -m webwright.skill_factory route \
  --task "..." \
  --library ./library \
  --primitive-site shopping_admin \
  --primitive-record ./run/primitive_retrieval.json \
  --start-url ...
```

Updater 在 MVP 中作为独立 Python API (`primitive_update.propose_updates/apply_updates`)
供元测试和实验 harness 调用；在 Phase 0 gate 通过前不接入默认 `learn/update` CLI。

## 10. 分阶段实现

### Phase 0：Oracle Pilot

- 人工构建一个可用网站的 primitive catalog（本轮因部署健康状态选择 Map）；
- 人工标注 held-out oracle primitives；
- 只实现 prompt injection 和 standalone final workflow；
- 比较 scratch 与 oracle primitives。

停止条件：

```text
至少 10 个 held-out task instances，覆盖至少 5 个 unseen templates。

Win  = scratch fail, oracle primitive pass
Loss = scratch pass, oracle primitive fail

GO:
  Win - Loss >= 2
  且 Win 来自至少 2 个不同 templates

NO-GO:
  Win <= Loss

INCONCLUSIVE:
  介于两者之间，增加样本或调整 primitive 表示/注入后重测
```

该 gate 暂时只看 WebArena task success，不把 steps/token 纳入标准。NO-GO 停止的是自动
updater/retriever 开发；先检查 primitive 粒度、注入 prompt 和任务选择。

### Phase 1：Primitive Retriever

- site filter；
- capability decomposition；
- LLM selection；
- requires/provides gap check；
- usage instrumentation；
- 与 oracle retrieval 比较。

### Phase 2：Primitive Updater

- 实现 ADD 和 NO_CHANGE；
- 用人工 workflow pairs/triples 测 boundary；
- candidate compile/schema checks；
- 再加入 MODIFY；
- 最后加入 SPLIT/ARCHIVE。

不要一开始同时实现所有 operations。

### Phase 3：End-to-End Evolution

- 按 template 顺序建立 catalog；
- 严格 cross-template WebArena evaluation；
- 加入 negative templates；
- 测 catalog growth、retrieval quality 和 downstream utility。

### Phase 4：Executable Confidence

只有 primitive code 已显示 downstream utility 后，才进入完整 release：

- standalone executable primitives；
- source-derived browser cases；
- shape/contract verification；
- shared imports 和 dependency manifests；
- selective replay 和 migration。

详见 [`cross_task_primitive_release.md`](cross_task_primitive_release.md)。

## 11. Future Plan：Executable Shared Package

未来如果实验表明：

- primitives 已经稳定；
- 相同代码被大量 workflows vendoring；
- 修复 primitive 后希望消费者自动获得收益；
- direct import 明显降低代码生成成本；
- bounded migration/replay 可承受；

再考虑：

```python
from skill_library.shopping_admin import get_product_reviews
```

届时才需要设计：

- stable public API；
- immutable versions 或 content-addressed releases；
- workflow dependency manifests；
- compatibility policy；
- selective migration；
- reverse dependency index；
- affected-workflow replay；
- rollback 和 deprecation。

这是一项独立的 package-management release，不属于 cross-task primitive reuse MVP。
完整计划见 [`cross_task_primitive_release.md`](cross_task_primitive_release.md)。

## 12. MVP 成功标准

MVP 成功不要求解决所有软件包维护问题。它需要证明：

1. Updater 能从不同 templates 中找到人工认可的共享网站单元；
2. Retriever 能在 unseen template 上找到相关 primitives；
3. Agent 能把 primitive code 融入完整 standalone workflow；
4. Retrieved primitives 相比 scratch 或 whole-workflow prior 提高成功率或降低成本；
5. Catalog 随 templates 增长时没有快速膨胀或检索退化；
6. 不依赖 runtime imports、版本图或全库 replay 也能完成上述闭环。

最小闭环：

```text
gold-admitted workflows from different templates
→ primitive ADD
→ unseen-template primitive retrieval
→ agent creates complete workflow
→ WebArena gold evaluation
→ new template-level workflow enters library
```

## 13. 当前实现（cross-template only）

本轮实现保持为一个很小的串行路由器：

```text
workflow metadata
  ├─ adapt → 只注入完整 workflow
  └─ skip  → primitive metadata
               ├─ use/adapt → 只获取并注入选中 primitive 的完整代码
               └─ skip      → scratch
```

- `route.py` 用 `--cross-template-workflow-first --primitive-site <site>` 启用该路径；
- primitive judge 只看到 capability、signature、requires/provides 和 patterns；
- code 只在 `use/adapt` 后按 ID 获取，`skip` 时不会进入 prompt；
- workflow 与 primitive 不在同一次 run 中混合；
- 输出记录 `route_stage`、`route_decision`、`remaining_gap` 和实际注入来源；
- same-template evaluation、budget-aware planning、executable/replay 与依赖管理均不在本轮。

相应单元测试覆盖 workflow 短路、workflow→primitive 回退、metadata skip 不泄露代码、
选中后完整注入、未知 ID 降级为 skip，以及旧 workflow 路由回归。

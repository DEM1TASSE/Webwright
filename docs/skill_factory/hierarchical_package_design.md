# Hierarchical Skill Package：由可执行复用关系长出的层级

> **Status: superseded for the MVP.** 当前实施方案见
> [`cross_task_primitive_mvp.md`](cross_task_primitive_mvp.md)。MVP 使用完整 standalone
> workflows 和仅在生成时检索的 primitive catalog，不实现 public hierarchy、runtime
> imports 或 dependency replay。**Vendoring 消除了 runtime dependency management，
> 因此 hierarchy 不再是 MVP 的必要条件。** 本文仅保留为早期 hierarchy design
> exploration；未来完整版见
> [`cross_task_primitive_release.md`](cross_task_primitive_release.md)。
>
> Design note。本文只讨论一个问题：如果 `skill = package`，package 应该采用固定双层
> `primitive → workflow`，还是支持 hierarchy？结论是：**数据模型使用可变深度的
> executable call DAG，首期实现限制为最多三级。**

## 1. 结论

不建议将 package 永久写死成：

```text
Primitive → Workflow
```

也不建议预设：

```text
Policy → Strategy → Procedure → Primitive
```

推荐：

```text
Package
└── executable exports DAG
    ├── leaf exports
    ├── composite exports
    └── workflow roots
```

所有可复用节点统一称为 `export`。它可以调用其他 exports：

- 没有内部依赖、直接操作页面或处理数据的叶子节点是 leaf export；
- 组合多个 exports、提供更高层网站能力的是 composite export；
- 面向最终任务、产生最终答案或 mutation 的根节点是 workflow。

层级来自真实调用关系，而不是来自预先规定的抽象名称。

第一版使用同一数据模型，但限制：

```text
max_depth = 3
min_consumers = 2
```

也就是：

```text
leaf export → composite export → workflow
```

这个限制是工程预算，不是理论上的层级定义。

## 2. 为什么固定双层不够

以 Shopping Admin reviews 为例：

```python
def open_product(product): ...

def open_product_reviews(product):
    open_product(product)
    ...

def get_product_reviews(product):
    open_product_reviews(product)
    return extract_review_rows()

def low_rating_reviews(product):
    reviews = get_product_reviews(product)
    return [r for r in reviews if r.rating <= 3]
```

自然调用关系是：

```text
open_product
  ← open_product_reviews
    ← get_product_reviews
      ← low_rating_reviews
```

如果只允许 primitive 直接连接 workflow，会产生两种问题：

1. workflow 必须重复编排 `open → navigate → paginate → extract`；
2. 为了避免重复，只能把整段都塞进一个过粗的 primitive。

允许 composite export 后，package 可以同时暴露不同但有用的调用粒度：

```text
open_product(product)
get_product_reviews(product) -> list[Review]
low_rating_reviews(product) -> list[Review]
```

新任务按需要选择，而无需为每组连续操作预建固定层级。

## 3. 为什么不预设四层 taxonomy

固定的 policy、strategy、procedure、primitive 层次适合组织供模型阅读的过程知识，但
不是 executable package 的必要条件。

Web package 中的层级更直接地由以下事实决定：

- 一个函数调用了哪些函数；
- 它接受和返回什么；
- 有多少 workflows 依赖它；
- 哪些真实 replay 验证过它；
- 修改它会影响哪些 dependents。

因此我们不需要回答“这个节点究竟是 strategy 还是 procedure”。我们只需要回答：

> 它是不是一个有稳定 contract、被多个消费者复用、能够通过执行验证的 export？

这也有助于与 SkillLens 的固定四层、多粒度 prompt-context routing 区分。我们的 hierarchy
是 executable dependency hierarchy，而不是 textual abstraction hierarchy。

## 4. 从 Workflows 建立 Hierarchy

假设三个 verified workflows 是：

```text
W1 = A → B → C → D
W2 = A → B → C → E
W3 = A → B → F
```

### 4.1 第一轮 factoring

所有任务共享 `A → B`，并且这段操作具有独立的网站语义：

```text
P1 = A → B

W1 = P1 → C → D
W2 = P1 → C → E
W3 = P1 → F
```

### 4.2 第二轮 factoring

W1 和 W2 继续共享 `P1 → C`：

```text
P2 = P1 → C

W1 = P2 → D
W2 = P2 → E
W3 = P1 → F
```

最终 call graph：

```text
P1
├── P2
│   ├── W1
│   └── W2
└── W3
```

`P2` 通过调用 `P1` 复用底层实现，不复制 `A → B`。

这里的 `P1`、`P2` 都只是 exports。是否把它们描述成 primitive、component 或 procedure，
不影响执行和验证。

## 5. 粒度的操作性定义

不把 granularity 定义成固定层数。一个候选 export 的粒度合适，当且仅当它满足：

1. **Semantic cohesion**
   完成一个可以清楚命名的网站能力，而不是任意连续代码片段。

2. **Stable contract**
   有明确输入输出；调用方不需要理解内部 selector、分页、重试或临时页面状态。

3. **Multiple consumers**
   被至少两个不同 `intent_template_id` 的 workflows 使用。

4. **Replay preserving**
   抽取和重写后，所有 dependent historical workflows 继续通过 replay。

5. **Measured utility**
   至少减少重复代码、agent 编排成本、browser exploration 或模型调用中的一项。

第一版可以将前四项作为发布门槛，第五项在 held-out evaluation 中测量。

### 5.1 太细

通常不应发布：

```python
click(selector)
wait_for_page()
read_text(selector)
```

这些是通用 browser wrappers，没有足够的网站语义，也会增加 retrieval 和 composition
噪声。

### 5.2 合适

更合理的 exports：

```python
open_gitlab_project(repo)
get_product_reviews(product) -> list[Review]
list_project_commits(repo) -> list[Commit]
route_between(origin, destination, mode) -> Route
```

### 5.3 太粗

如果一个 export：

- 只服务一个最终 task；
- 同时做导航、抽取、过滤、格式化和 mutation；
- 拥有大量 `task_type` 条件；
- 输入参数大部分只在某个分支使用；

那么它更可能是 workflow，而不是共享 export。

## 6. 什么时候创建 Composite Export

不要因为两个函数相邻就创建中间层。只有当一组 exports：

1. 在至少两个不同模板的 workflows 中重复组合；
2. 组合本身有独立、可命名的网站语义；
3. 能定义稳定输入输出；
4. 抽取后减少实际重复或隐藏不稳定状态处理；
5. 所有 dependents replay 通过；

才提升为 composite export。

例如：

```text
open_product
+ open_reviews_tab
+ paginate_reviews
+ parse_review_rows
```

可以提升为：

```python
get_product_reviews(product) -> list[Review]
```

但：

```text
click_button
+ sleep
+ read_text
```

只是偶然相邻，不应该形成 composite export。

## 7. 最小数据模型

```python
class Export:
    name: str
    description: str
    inputs: dict
    output_schema: dict
    calls: list[str]
    source_templates: list[int]
    replay_cases: list[str]
    kind: str  # "export" | "workflow"
```

概念上的 metadata：

```yaml
package: shopping_admin_reviews

exports:
  - name: open_product
    calls: []
    inputs:
      product: string
    output: ProductPage
    source_templates: [249, 250, 288]

  - name: get_product_reviews
    calls:
      - open_product
      - open_reviews_tab
      - extract_review_rows
    inputs:
      product: string
    output: list[Review]
    source_templates: [249, 250, 288]

workflows:
  - name: low_rating_reviews
    calls:
      - get_product_reviews
      - filter_reviews
    source_templates: [249]
```

调用图必须是 DAG：

- 禁止循环依赖；
- package 发布前检查所有 `calls` 可解析；
- workflow 可以依赖 exports；
- export 可以依赖更低层 exports；
- leaf export 的 `calls` 为空。

## 8. Code Agent 如何选择粒度

第一版不要让 agent 优化复杂的全局 hierarchy。给它局部、可验证的 refactoring 任务：

> Given verified programs from different task templates on the same website, extract
> the smallest set of website-semantic functions that removes meaningful duplication
> across workflows. An export may call existing exports. Keep task-specific filtering,
> aggregation, formatting, and mutations in workflow roots. Do not extract generic
> browser wrappers or create an export used by only one workflow. Every export must
> have a clear input/output contract.

明确三条边界：

```text
不要太粗：
  不把完整历史任务换名后当作 shared export。

不要太细：
  不抽取 click、wait、read_text 等 generic wrappers。

优先抽取：
  被不同模板重复使用、有网站语义、contract 稳定的调用子图。
```

Agent 可以提出候选，但 replay 决定是否接受。不要让同一个生成判断直接成为发布依据。

## 9. Bottom-Up 构建算法

```text
输入：同网站、不同模板的 verified workflows

1. Normalize
   将 scripts 转为带函数边界、数据流和页面效果的候选调用单元。

2. Find shared regions
   找至少被两个不同模板使用的候选代码片段或调用子图。

3. Extract leaves
   先抽取有网站语义、contract 稳定的底层 exports。

4. Rewrite
   让来源 workflows 调用候选 exports。

5. Replay
   回放全部 dependents；任何失败都拒绝候选。

6. Factor again
   在更新后的 graph 中寻找重复的 export compositions。

7. Create composites
   只有组合具有独立语义和多个 consumers 时才创建中间 export。

8. Stop
   无新候选、无可测收益，或达到首期 max_depth 时停止。
```

伪代码：

```python
graph = workflows

while graph.depth < max_depth:
    candidates = propose_shared_subgraphs(graph)
    candidates = [
        c for c in candidates
        if c.consumer_template_count >= 2
        and c.has_website_semantics
        and c.has_stable_contract
    ]

    candidate = choose_minimal_candidate(candidates)
    if candidate is None:
        break

    rewritten = factor(graph, candidate)
    if replay_all_dependents(rewritten):
        graph = rewritten
    else:
        reject(candidate)
```

第一版可以每轮只尝试一个候选，避免全局组合搜索。

## 10. Verification

修改一个 export 后，沿反向调用图找到全部 dependent workflows：

```text
changed export
→ direct callers
→ transitive callers
→ workflow roots
→ replay every affected workflow
```

例如：

```text
extract_review_rows changed
  → get_product_reviews
    → low_rating_reviews
    → count_keyword_reviews
    → update_description_from_rating
```

以上 workflows 都必须 replay。未受影响的 package 可以不回放。

首期只要求 workflow-level replay。未来再添加：

- export 中间输出 gold；
- contract/property tests；
- mock page unit tests；
- 多环境 compatibility matrix。

## 11. Retrieval

新任务检索的是 exports，不是抽象层标签：

```text
task
→ site filter
→ capability match
→ contract compatibility
→ verification evidence
→ selected exports
```

retrieval 可以返回不同深度的节点。例如：

- 简单任务直接使用 `get_product_reviews`；
- 特殊任务需要更底层的 `open_reviews_tab` 和 `extract_review_rows`；
- 完全匹配时可以直接运行 workflow root。

首期不需要自动遍历 hierarchy 来决定 `decompose/rewrite/skip`。可以：

1. 检索少量相关 exports；
2. 向 agent 展示 signature、调用关系和实现；
3. 由 agent 选择调用；
4. 记录实际使用情况。

这能避免重复 SkillLens 的 adaptive multi-granularity routing，同时测试 executable hierarchy
是否真的有用。

## 12. 与 SkillLens 的核心区别

| SkillLens | Hierarchical Skill Package |
|---|---|
| 固定 policy/strategy/procedure/primitive 四层 | 不预设层名和深度 |
| textual procedural units | executable exports |
| hierarchy 表示抽象层次 | hierarchy 表示真实调用和依赖 |
| query-time accept/decompose/rewrite/skip | library-time factoring + dependency replay |
| 拼成 context 后由模型消费 | exports 可以直接调用和 standalone 执行 |
| verifier 选择当前任务的 adaptive frontier | historical consumers 决定是否发布抽象 |

因此，不应把贡献描述为“我们提出多粒度 hierarchical skills”。更准确的是：

> We induce an executable package hierarchy from cross-task reuse dependencies and
> admit each refactoring only when all affected workflows continue to pass replay.

## 13. 最小实现路线

### Step 1：使用通用 DAG schema

即使首个 package 只有 leaf exports 和 workflows，也从一开始记录 `calls`，不要把存储格式
写死为双层。

### Step 2：人工构建一个三级 package

用 Shopping Admin reviews 构建：

```text
open_product / extract_review_rows
  → get_product_reviews
    → low_rating_reviews / keyword_count / description_update
```

确认：

- contracts 能连接；
- workflow replay 可运行；
- agent 能选择不同深度 exports。

### Step 3：自动抽取 leaf exports

先只自动发现不同模板间直接重复的网站语义操作。

### Step 4：自动抽取一个 composite export

在已有 exports 的重复调用序列中提出一个 composite，回放 dependents 后决定是否接受。

### Step 5：根据实验决定是否增加深度

只有当三级限制阻碍实际 WebArena tasks 时，才提高 `max_depth`。不要把更深 hierarchy
本身当成目标。

## 14. 最终选择

三个方案中：

| 方案 | 优点 | 问题 | 选择 |
|---|---|---|---|
| 固定双层 | 最容易实现 | 很快产生重复编排或过粗 primitives | 不作为长期数据模型 |
| 固定四层 taxonomy | 表达丰富 | 预设过强，与 SkillLens 重叠 | 不采用 |
| 可变深度 call DAG | 简洁、可扩展、符合 package 语义 | 需要 dependency/replay traversal | 采用 |

工程上采用“通用 DAG + 首期最多三级”：

```text
数据模型不锁死未来
+ 当前实现和评测仍然足够简单
+ hierarchy 由 verified reuse 证据生长
```

# Cross-Task Web Skills：从任务脚本到可演化的软件包

> **Implementation status.** 本文保留完整 research brainstorm；当前收敛后的 MVP 规格见
> [`cross_task_primitive_mvp.md`](cross_task_primitive_mvp.md)。若两者在 runtime imports、
> hierarchy、versioning 或 replay 上冲突，以 MVP 文档为准。
>
> Brainstorm / design note。本文整理 Web Skill Factory 从“同一任务模板内复用”走向
> “同一网站、不同任务之间复用”的研究动机、概念模型、评测协议和最小实现路线。
> 它不是最终规格；首要原则是让实现服从研究问题和评测证据，而不是为了覆盖软件工程术语而过度设计。

## 1. 背景：当前系统解决了什么

当前 Web Skill Factory 的基本单位是一类任务模板。多个已验证实例被对齐，实例之间
变化的内容被提升为参数或页面 pattern，最终形成一个可执行的、参数化的完整程序：

```text
同模板实例 P(x=a) + P(x=b)
                ↓ 对齐、参数化、验证
             一个 workflow P(x)
```

例如，“查询用户在某一天向某仓库提交了多少 commits”可以通过 `user`、`date` 和
`repo` 参数覆盖同一模板的其他实例。这种复用主要回答：

> 一个已经解决的任务模板能否泛化到该模板的新参数？

已有 WebArena 实验也是这一 setting：每个模板用 3 个训练实例建立一个 skill，再在
同模板的 2 个 held-out 实例上测试。

这套表示对同模板泛化有效，但对同网站上的不同任务过于粗。例如：

- 查询某产品的低星评论；
- 统计包含关键词的评论；
- 根据高星评论数量更新产品描述。

它们不是同一模板，不能靠给一个完整 workflow 增加参数来合理合并；但它们显然可能
共享产品定位、评论页导航、分页和评论抽取逻辑。

## 2. 新问题：Cross Task in the Same Website

新的研究问题是：

> 同一网站上、不同任务产生的 verified programs，能否被组织成可维护的软件包，
> 让未见过的新任务检索并部分复用其中合适粒度的能力？

这里有三个关键变化：

1. **评测隔离单位改变。** held-out 必须是训练阶段未见过的 `intent_template_id`，
   不能只是同模板的新 task ID。
2. **复用对象改变。** 新任务可能只需要历史程序的一部分，而不是整个 task skill。
3. **合并操作改变。** 系统不再只给完整 workflow 添加参数，而要从多个 workflow 中
   提取共享能力，同时保留各自的任务逻辑。

因此，目标不是机械地把所有脚本拆成原子函数，也不是把同网站的所有任务塞进一个带
大量 `task_type` 分支的巨型 skill。真正的问题是：

> 对当前网站和任务集合，什么是合适的可复用边界？

两个任务之间可能有多种关系：

- 完全共享一个操作；
- 同一操作只需要参数化；
- 只共享导航前缀；
- 共享 extraction，但 filter / aggregation 不同；
- 共享抽象能力，但页面实现不同；
- 没有重复实现，却可以首尾组合；
- 看似相似，但合并后分支和回归风险大于收益。

第一版不需要一次性解决所有粒度。它需要证明：比“完整 task skill”更细的、
具有明确接口的复用单元，能在严格的 cross-template evaluation 中带来收益。

### 2.1 与 SkillLens 的边界

这里的 “SkillLens” 指 Miao et al. 的
[SkillLens: Adaptive Multi-Granularity Skill Reuse for Cost-Efficient LLM Agents](https://arxiv.org/abs/2605.08386)，
不是微软同名的 model-generated skill lifecycle study。

SkillLens 已经直接研究了以下问题：

- 将 skill 组织为 policy、strategy、procedure、primitive 四层图；
- 对完整 skill 做不同粒度的局部兼容性判断；
- 用 embedding seed retrieval 和 degree-corrected random walk 扩展候选；
- 对候选单元执行 `ACCEPT / DECOMPOSE / REWRITE / SKIP`；
- 将保留或局部改写的文本单元拼成 task-specific context，再交给模型推理；
- 根据 evolution split 上的失败报告，以 `ADD / DELETE / UPDATE / MERGE` 演化 registry；
- 在 MuLocBench 和 ALFWorld 上评估 mixed-granularity reuse。

因此，以下表述不能作为我们的主要 novelty：

- “完整 skill 太粗，所以应该支持多粒度 skill”；
- “根据任务只检索 skill 的一部分”；
- “对兼容部分保留，对不兼容部分局部改写”；
- “建立层次 skill graph，再做 adaptive granularity routing”；
- “自动决定 accept、decompose、rewrite 或 skip”。

这些都与 SkillLens 的核心问题和机制高度重叠。我们可以把它作为直接 related work 或
强 baseline，但不能只换成 web setting 后重复其 framing。

我们的候选边界应落在 **artifact、merge semantics 和 verification contract**：

| 维度 | SkillLens | 本项目候选方向 |
|---|---|---|
| skill 的主要形态 | 带层次关系的 textual procedural units；最终组成 prompt context | 可导入、可调用、可独立运行的 code package |
| 层次结构 | 固定四层：policy / strategy / procedure / primitive | 不预设四层；package 只区分 public exports、private implementation 和 workflows |
| inference-time use | verifier 选择、展开或改写单元，拼入 prompt，由模型完成任务 | 优先调用已验证 exports；模型只负责新 workflow 和无法复用的部分 |
| adaptation | 针对当前 query 局部 rewrite，构造新的 context | 对 library 做 API-preserving refactoring，产生可持久化 package 更新 |
| merge 的语义 | registry 单元的 add/delete/update/merge，优化下游 utility | 从多个 executable workflows 中诱导稳定接口，抽取共享实现并重写 dependents |
| verification | LLM verifier 路由；evolution/validation split 上比较终局任务指标 | 实际执行 export/workflow，并 replay 所有 dependent historical tasks |
| correctness guarantee | skill context 是否帮助 agent 获得更好终局表现 | package 更新是否保持既有可执行行为，并能 standalone 重现记录结果 |
| 主要成本目标 | 减少检索、rewrite 和 prompt consumption 成本 | 降低重复 browser exploration/model use，同时保持软件包可维护性 |
| 评测环境 | MuLocBench、ALFWorld | WebArena 同网站、严格 cross-template 的真实网页状态与 mutation |

最重要的差异不是“我们的 granularity 比它更好”，而是：

> SkillLens 选择和改写供模型消费的多粒度过程知识；我们研究如何把多个已验证的
> web programs 安全地重构成拥有稳定 API 的 executable package，使新任务能够调用
> 其中部分实现，并让 package 更新对所有历史 dependents 继续通过真实执行 replay。

这仍然需要实验证明，而不是仅靠 artifact 形式宣称差异。尤其要证明：

1. executable export 相比同内容的 textual procedure 有额外收益；
2. replay-verified refactoring 相比 query-time local rewrite 更可靠或更便宜；
3. package API 能在不同 WebArena templates 间被直接调用，而不只是作为 agent 提示；
4. shared export 更新后的 dependent replay 能捕获普通终局 validation 不容易发现的回归。

因此，SkillLens 应加入 baseline：

```text
Textual multi-granularity baseline:
  将相同历史 workflows 拆成 procedure/primitive 文本
  → 为测试任务选择兼容单元
  → 拼入 agent prompt

Executable package:
  从历史 workflows 抽取 verified exports
  → 为测试任务检索 exports
  → 直接调用或由 agent 编排调用
```

如果 executable package 不能超过这个 baseline，那么 `skill = package` 主要只是工程形态，
尚不足以构成研究贡献。

## 3. 统一理念：Skill = Package

我们把 skill 视为一个软件包，而不是一份平铺脚本或一段供模型阅读的说明：

```text
Skill Package
  = public exports
  + task workflows
  + private implementation
  + typed/structured contracts
  + verification replays
  + provenance and metadata
```

这个定义首先是一条设计原则。它不要求第一版立即实现 Python 继承体系、复杂依赖解析器
或完整 semantic versioning。

### 3.1 软件工程概念与 Skill Factory 的对应关系

| 软件工程概念 | 在 Skill Factory 中的含义 | 第一版是否必需 |
|---|---|---|
| Package | 同一网站或任务域内，可独立检索、执行、验证和演化的一组能力 | 必需 |
| Public API / exports | 可供新 workflow 部分复用的函数，以及输入、输出和适用条件 | 必需 |
| Encapsulation | workflow 不依赖 DOM selector、分页、重试和登录等内部细节 | 必需，但只做最小边界 |
| Composition | 新任务组合一个或多个 exports 完成新的 workflow | 必需，第一版可由 agent 完成 |
| Regression tests | package 更新后回放所有受影响的历史任务 | 必需 |
| Provenance | export 来源于哪些 verified runs / templates | 必需 |
| Interface / schema | export 的结构化输入输出和最小前置条件 | 必需 |
| Inheritance | 将子任务的稳定实现上提到网站或任务族父类 | 可选 |
| Polymorphism | 同一能力接口拥有多个页面或策略实现 | 可选，出现真实需求后再加 |
| Dependency management | package/workflow 依赖哪些 exports 或其他 package | 简单记录必需；版本求解可选 |
| Semantic versioning | 根据接口兼容性管理 package 版本 | 可选 |
| Unit tests | 对 primitive 的局部页面行为进行隔离验证 | 可选；端到端 replay 优先 |

### 3.2 为什么不把继承、多态作为首期目标

继承、多态和封装可以帮助解释 `skill = package`，但研究贡献不应是逐项复刻面向对象
特性。只有实际 evaluation failure 要求某个机制时，才实现它：

| 观察到的失败 | 再引入的机制 |
|---|---|
| 同一逻辑只差输入值 | 参数化 export |
| 同一 contract 有多个 DOM 实现 | 多实现选择 / 多态 |
| workflow 依赖过多 selector 细节 | 加强封装和 public/private 边界 |
| 多个 exports 无法连接 | 统一中间 schema |
| 修改共享函数破坏旧任务 | dependency-aware regression replay |
| package 变成大量条件分支 | split / specialize |

换言之，软件工程规范是帮助我们形成稳定抽象和安全演化的工具，而不是 feature checklist。

## 4. 从 WebArena 任务观察到的复用粒度

本地 `webarena-verified` 数据集包含 812 个任务、191 个模板。其中单网站任务包括：

| 网站 | 任务数 |
|---|---:|
| Shopping | 187 |
| Shopping Admin | 182 |
| GitLab | 180 |
| Map | 109 |
| Reddit | 106 |

数据里至少存在三档 cross-task transfer。

### 4.1 Easy：相同数据源，不同 filter / aggregation

GitLab commits 相关模板：

- Template 322：某用户在某 repo、某天的 commit 数量；
- Template 321：当前 repo 中某用户在某时间段的 commit 数量；
- Template 323：repo 中 commit 最多的用户；
- Template 324：repo 的前三名 contributor 属性。

候选共享 exports：

```python
open_project(repo)
navigate_to_commits()
collect_commit_pages()
extract_commits() -> list[Commit]
```

task-specific 逻辑：

```python
count_by_user_and_date(commits, user, date)
count_by_user_and_period(commits, user, period)
top_contributors(commits, k)
```

这是一组很好的 smoke test，但它接近原有参数泛化，不能单独承担主结论。

### 4.2 Medium：共享 extraction，任务结果或动作不同

Shopping Admin reviews 相关模板：

- Template 249：取三星及以下评论的 title/rating；
- Template 250：取四星及以上评论的 title/rating；
- Template 288：统计包含某关键词的评论数；
- Template 244：获取对产品最不满意的客户信息；
- Template 251：根据高星评论数更新产品描述。

候选 package：

```python
find_product(product)
open_product_reviews(product)
extract_reviews() -> list[Review]
filter_reviews(reviews, min_rating=None, max_rating=None, keyword=None)
```

这组任务允许测试：

- retrieve → retrieve transfer；
- retrieve → mutate transfer；
- 只复用 package 的一部分，而不是复用完整历史 workflow；
- extraction、aggregation 和 mutation 之间的清晰边界。

它比 commits family 更能体现 cross-task package reuse，适合作为第一组主实验。

### 4.3 Hard：共享 primitives，需要重新组合

Map 相关模板：

- Template 46：查询地点坐标；
- Template 68：查询两地步行时间；
- Template 36：查询两地最短驾车时间；
- Template 69：查询某地点附近最近的一类地点；
- Template 501：获取地点属性；
- Template 73：同时查询步行和驾车时间。

候选 exports：

```python
geocode(query) -> Coordinates
search_nearby(category, center) -> list[Place]
route(origin, destination, mode) -> Route
place_details(place) -> PlaceDetails
```

新任务可能需要：

```python
center = geocode(location)
hotels = search_nearby("hotel", center)
routes = [route(center, hotel, mode="walking") for hotel in hotels]
```

这里主要测试跨 workflow composition，而不是相似完整程序的参数化。

## 5. Cross-Task Merge 是什么

### 5.1 与 Same-Template Merge 的区别

Same-template merge：

```text
找到变化
→ 将变化提升为参数或 pattern
→ 保留一个完整 workflow
```

Cross-task merge：

```text
找到不同 workflows 依赖的稳定能力
→ 将该能力提升为 public export
→ 保留不同的 task workflows
→ 用 replay 验证重构没有改变历史行为
```

如果：

```text
P1 = A → B → C → D
P2 = A′ → B′ → C′ → E
```

且 `B→C` 与 `B′→C′` 能被泛化为共享能力 `S`，合理结果是：

```text
S = generalize(B → C, B′ → C′)
P1′ = A  → S → D
P2′ = A′ → S → E
```

而不是：

```python
def giant_skill(task_type, user=None, date=None, product=None, ...):
    if task_type == ...:
        ...
```

### 5.2 长期可用的 merge / refactoring 元操作

这些操作描述完整设计空间，但首期只实现其中一个子集。

1. **Extend / Parameterize Method**
   workflow 相同，只扩展参数、selector pattern 或局部分支。当前系统已经主要支持。

2. **Factor / Extract Method or Package**
   从不同 workflows 中提取共享 responsibility，形成 public export。

3. **Lift Interface / Introduce Interface**
   对输入输出略有差异的片段建立统一结构化 contract。

4. **Split**
   现有 task skill 太粗，先拆出共享组件，再让不同 workflows 引用它。

5. **Compose**
   两个 exports 没有重复代码，但可以首尾连接；只新增组合关系，不合并源码。

6. **Specialize / Replace Conditional with Polymorphism**
   共享实现分支过多或回归不稳定时，拆成多个兼容实现。

7. **Keep Separate**
   候选抽象没有收益，或复杂度和风险大于复用价值；记录相关性但不修改 package。

一个健全的 merge 必须允许 no-op。自动系统不应该被迫为每对相似代码制造抽象。

### 5.3 首期最小 merge

第一版只需要一个受控的 refactoring：

```text
Extract Shared Export
  1. 输入同网站的多个 verified programs
  2. 提出一个候选共享 responsibility
  3. 生成带输入输出 schema 的 export
  4. 让历史 workflows 使用或独立 replay 该 export
  5. 回放所有来源任务
  6. 全部通过才发布 package 更新；否则保持原状
```

首期不需要自动完成任意 `split → factor → specialize` 搜索，也不需要构建深层继承树。

## 6. Package 的最小数据模型

建议保持目录结构简单，并与当前 library 兼容：

```text
library/
└── shopping_admin_reviews/
    ├── package.py
    ├── meta.json
    └── replays.json
```

`package.py` 包含 public exports 和必要的 private helpers。task workflow 可以暂时继续由
agent 生成，不必全部持久化为独立类。

`meta.json` 的概念结构：

```json
{
  "package_id": "shopping_admin_reviews",
  "site": "shopping_admin",
  "summary": "Navigate, extract, and filter product reviews in Shopping Admin.",
  "exports": [
    {
      "name": "get_product_reviews",
      "description": "Return normalized reviews for a product.",
      "inputs": {
        "product": "string"
      },
      "output_schema": {
        "type": "array",
        "items": {"$ref": "Review"}
      },
      "preconditions": ["authenticated"],
      "source_templates": [249, 250, 288],
      "verified_replays": ["task-213", "task-119", "task-11"]
    }
  ]
}
```

第一版 contract 最少需要：

- export 名称；
- 一句话语义描述；
- 参数名称；
- 结构化输出 schema；
- 来源网站；
- 来源 templates / runs；
- replay 验证状态。

以下内容暂时可选：

- 完整 precondition/postcondition 语言；
- package 依赖版本范围；
- 多个实现的 dispatch policy；
- semantic version；
- 独立 unit-test harness。

## 7. Retrieval 与 Use

当前 retrieval 主要选择完整 skill，并输出 `run / adapt / skip`。cross-task package 需要支持
export-level retrieval：

```text
task query
  → retrieve website packages
  → rank relevant exports
  → return selected signatures + implementations + provenance
  → agent composes/adapts them into the new workflow
```

第一版不必让系统自动规划和执行任意 function graph。可以让 agent 获得：

- package summary；
- 选中的 export 名称和 signature；
- export 的实现或明确调用方式；
- 适用网站和验证来源；
- “可以只使用这些 exports，不需要复用完整 workflow”的提示。

这样能回答一个比“多粒度 retrieval 是否有效”更具体的问题：**可执行、带 contract 且
经过 replay 的 package export**，是否比 whole-skill reuse 和同内容的 textual subskill
更有用。

后续如果 agent 经常选对 exports 却无法组合，再实现：

- 显式依赖图；
- 中间 schema compatibility；
- 自动 composition planner；
- execution-time dispatch。

### 7.1 Retrieval 不应只依赖文本相似度

首期检索可由以下信号组合：

1. 网站必须兼容；
2. task 描述与 export capability 的语义相关性；
3. 输入实体是否能映射到 export 参数；
4. export 输出是否可能支持目标任务；
5. verification coverage 和历史成功率；
6. 提供整个 package 的成本。

仍然可以使用 LLM 做最后选择，但返回单元应是 exports，而不是只能选择一个完整 skill。

## 8. Verification 与安全演化

“Skill = package”的核心价值不只是代码组织，而是 package 级维护纪律：

```text
任何共享 export 的更新
→ 找到所有来源和依赖 replays
→ 回放受影响任务
→ 全部通过后提交
```

首期验证分为两层：

1. **Export replay**：export 能否在来源实例上产生 workflow 所需的结构化中间结果；
2. **Workflow regression**：原任务的最终答案或 mutation evaluator 是否仍通过。

如果暂时难以记录中间 gold，第一版可以只做 workflow regression。它证明重构没有破坏
历史行为，但不能精确定位 export 的局部错误。中间结果验证可以作为下一阶段增强。

接受一个抽象至少需要：

```text
valid:
  所有来源 task replays 通过

grounded:
  export 来自至少两个真实的 verified workflows/templates

useful:
  在 cross-template held-out task 中被实际选择或使用
```

不要仅凭静态代码相似度发布共享 export。

## 9. Evaluation Protocol

### 9.1 Split 原则

新的 held-out 维度必须是模板：

```text
Train:
  同网站上的若干 intent_template_id

Test:
  同网站、但完全未参与 package 构建的 intent_template_id
```

需要额外避免：

- 同一个实体或页面在 train/test 中造成过强泄漏；
- 训练模板和测试模板只是措辞不同但实际 evaluator 完全相同；
- 只选择容易共享的正例，缺少“不应合并”的负例；
- 将模型已有的网站知识误记为 package transfer 收益。

### 9.2 难度分层

| 难度 | Train/Test 关系 | 主要能力 |
|---|---|---|
| Easy | 相同数据源，不同 filter / aggregation | export extraction |
| Medium | 共享 extraction，但输出或动作不同 | partial reuse |
| Hard | 只共享底层 primitives，测试任务需要新组合 | composition |
| Negative | 同网站但没有值得共享的实现 | correct skip / no merge |

### 9.3 Baselines

至少比较：

1. **Scratch**：无 library。
2. **Whole-task retrieval**：当前完整 skill prior。
3. **Package retrieval**：只提供检索到的 public exports。
4. **Oracle exports（诊断上界）**：人工指定正确 exports，隔离 retrieval 与 use 的问题。
5. **SkillLens-style textual units**：将相同经验表示为多粒度 procedure/primitive 文本，
   选择相关单元后拼入 prompt，隔离 executable package 相对多粒度 context 的增益。

如果预算允许，再加入：

6. **All website code**：把同网站所有历史代码都给 agent，测试精确 retrieval 是否真的必要。
7. **Whole textual procedures**：提供完整自然语言步骤，区分代码复用与一般提示收益。

### 9.4 指标

主要指标：

- WebArena evaluator success；
- agent steps / API calls；
- token 和 wall-clock cost；
- held-out template 的平均表现。

机制诊断：

- export retrieval precision / recall；
- 实际使用的 exports；
- exports 来自多少不同训练模板；
- agent 新写代码与复用代码的比例；
- retrieved-but-unused 比例；
- composition / invocation failure；
- package 更新后的历史 regression；
- no-merge 负例上的误合并率。

### 9.5 推荐的第一组实验

优先使用 Shopping Admin reviews：

```text
Train templates:
  249  三星及以下评论
  250  四星及以上评论
  288  包含关键词的评论数

Test templates:
  244  最不满意客户的信息
  251  根据高评分评论数修改产品描述
```

理由：

- 核心 review extraction 有真实共享空间；
- task intent 和最终输出明显不同；
- 同时覆盖 retrieve → retrieve 与 retrieve → mutate；
- 不能合理地用“给完整 workflow 添加几个参数”解释；
- 能直接观察部分 export 复用。

随后加入：

- GitLab commits 作为 easy/smoke tier；
- Map geocode/search/route 作为 hard/composition tier；
- 同网站但页面责任无关的任务作为 negative tier。

## 10. 必需 Features 与可选 Features

### 10.1 第一版必须实现

1. **Package representation**
   - 一个 package 可以包含多个 public exports；
   - exports 与完整 task workflow 分离。

2. **Export contracts**
   - 名称、描述、参数、输出 schema、网站和 provenance。

3. **Cross-task extraction**
   - 从至少两个不同 templates 的 verified programs 中提出并生成共享 export。

4. **Partial retrieval**
   - 针对新任务返回相关 exports，而非只能返回一个完整 skill。

5. **Agent-side partial use**
   - agent 能调用、复制或局部适配所选 exports 来完成新 workflow。

6. **Regression replay**
   - package 更新必须回放所有来源任务；
   - 失败时保留旧 package 或不合并。

7. **Strict cross-template eval**
   - train/test 的 `intent_template_id` 不重叠；
   - 保留 scratch 和 whole-skill baselines。

8. **Usage instrumentation**
   - 记录检索了什么、实际使用了什么，以及复用来源。

### 10.2 建议但可以稍后实现

- 中间结果的 export-level verification；
- package 内简单 dependency graph；
- 参数化 exports；
- package public/private visibility；
- negative/no-merge decision；
- retrieval 的 schema compatibility 信号；
- 自动生成多个 merge candidates 后择优。

### 10.3 暂时不需要

- 深层 class inheritance；
- 完整 polymorphic dispatch framework；
- 跨 package semantic-version solver；
- 通用自动 program synthesis / arbitrary composition planner；
- 所有函数的原子化拆分；
- 完整 unit/integration test 框架替代 replay；
- 自动优化全局 package graph；
- 为每个软件工程术语单独实现一个 feature。

## 11. 最小实现路线

### Phase 0：冻结问题和数据切分

目标：在改系统前确定可证伪的实验。

- 选定 Shopping Admin reviews 的 train/test templates；
- 检查实体和页面泄漏；
- 为每个测试任务人工标注可能复用的 exports，作为 oracle；
- 运行或整理 scratch / whole-skill baseline；
- 定义成功、步骤、token 和 export-use 记录格式。

交付物：

```text
cross_task_split.json
oracle_exports.json
baseline_results.json
```

### Phase 1：手工 package + Oracle 使用

目标：先验证“package exports 对这些任务是否真的有用”，再自动化 extraction。

- 从已有 verified scripts 手工抽取 2–4 个 review exports；
- 为每个 export 写最小 metadata；
- 在测试任务 prompt 中提供人工指定的正确 exports；
- 与 scratch 和 whole-skill 比较。

这一阶段非常重要。如果 oracle exports 都不能提升结果，问题不在自动 merge 或 retrieval，
继续建设复杂 Factory 没有意义。

交付物：

```text
一个 shopping_admin_reviews package
oracle partial-reuse results
失败案例分类
```

### Phase 2：Partial Retrieval

目标：从“人工指定 exports”走向“系统选择 exports”。

- library 能索引 package 和 exports；
- retrieval 先按 site 过滤，再按 task/capability 排序；
- decision 返回若干 exports 及 reuse instructions；
- 记录 retrieved / used / failed exports；
- 与 oracle 上界比较，区分 retrieval failure 和 use failure。

交付物：

```text
export-level retrieve/recommend
package-aware prompt
retrieval diagnostics
```

### Phase 3：自动 Extract Shared Export

目标：自动完成最小 cross-task merge。

- 输入不同 templates 的 verified scripts 和 metadata；
- LLM 提出共享 responsibility、signature 和实现；
- 写入临时候选 package；
- 回放所有来源任务；
- 全部通过才发布；
- 失败则 reject 或保留为未验证 reference，不覆盖现有 package。

首期只生成一个或少量候选，不做全局最优搜索。

交付物：

```text
cross-task learn/update path
candidate package patch
source-template regression replay
```

### Phase 4：扩展难度和按失败补机制

目标：确认结果不局限于 reviews。

- GitLab commits：验证 easy tier；
- Map：验证 composition tier；
- negative pairs：验证系统不会强制合并；
- 根据真实 failure 决定是否增加参数化、多实现、schema compatibility 或 dependency graph。

## 12. 研究 Story

可以将论文或项目叙事组织为：

### 12.1 Problem

现有 code skill 往往以完整任务程序为单位。同模板的新实例可以通过参数化复用，但网站内
的新任务通常只与历史程序部分重叠。已有 SkillLens 已从 prompt-context 角度解决多粒度
选择和局部改写；仍未解决的是，如何把不同任务的 executable web programs 安全重构为
可持久化、可调用且不破坏既有消费者的软件包。

### 12.2 Insight

Cross-task code reuse 不是单纯选择更细的 prompt 单元，而是一个 API induction 和
behavior-preserving refactoring 问题。Web skills 更适合作为可演化的软件包：package
暴露经过验证的能力接口，同时封装脆弱的页面实现；不同 task workflows 可以直接调用
所需 exports。

### 12.3 Method

从不同任务的 verified programs 中提取共享 export，记录结构化 contract 和 provenance，
通过历史 regression replay 约束 package refactoring；对新任务执行 export-level
retrieval，优先直接调用 verified code，由 agent 只编排新 workflow 或补齐缺失部分。

### 12.4 Evidence

在同网站、严格 cross-template 的 WebArena split 上，比较 scratch、完整 task skill、
SkillLens-style textual units、package exports 和 oracle exports，测量成功率、成本、
直接函数调用、standalone coverage 和 dependent regression。

### 12.5 克制的 claim

第一版不需要声称解决了通用的自动软件架构设计。更准确的 claim 是：

> We formulate cross-task web-skill learning as replay-verified package refactoring:
> inducing callable APIs from multiple executable workflows, reusing their exports on
> unseen task templates, and preserving the behavior of every dependent task.

## 13. 决策原则

后续设计应持续遵守：

1. **Eval first。** 没有 held-out template 上的需求，不增加架构复杂度。
2. **Package is a boundary, not a class hierarchy。**
3. **Prefer composition over giant conditional workflows。**
4. **抽象由多个 verified consumers 支撑，而不是由表面代码相似度支撑。**
5. **任何 merge 都必须允许 no-op。**
6. **历史 replay 是发布共享代码的最低门槛。**
7. **先证明 oracle partial reuse 有效，再自动化 merge 和 retrieval。**
8. **根据失败案例增加参数化、多态或依赖机制，而不是提前实现。**

## 14. 当前建议

最合理的下一步不是立即重构整个 Skill Factory，而是完成一个最小纵向闭环：

```text
Shopping Admin 的不同 review templates
  → 人工整理一个含少量 exports 的 package
  → 在未见模板上 oracle partial reuse
  → 验证有效
  → export-level retrieval
  → 自动 Extract Shared Export
  → regression replay
  → 扩展到 GitLab 和 Map
```

这个顺序既保留了 `skill = package`、可维护、可扩展、可抽象的统一理念，也确保每个
新增 feature 都由具体需求和 evaluation protocol 支撑。

# Cross-template 站点 Primitive：实验、分析与更新后的 Pipeline

日期：2026-08-10

分支：`cross-task-primitives`

[English version](cross_template_primitive_experiment_and_pipeline_2026-08-10.md)

## 1. 我们在评估什么

目标场景是：**同一网站内、跨 task template 的能力复用**。我们用某网站上通过 gold gate
的 workflow 建库，再在同网站未参与建库的 held-out templates 上评估。

这里区分三个概念：

- **Workflow**：某个 task template 的完整、独立解决方案，保存完整代码。
- **Primitive**：站点相关、可以跨 template 复用的采集或解析操作，例如列出 GitLab
  commits、解析 Magento review detail。
- 当前任务的筛选、比较、排序、聚合、语义判断和最终答案格式仍属于 workflow/task 层。

MVP 中，检索到的 primitive 代码会被复制进最终的 standalone `final_script.py`。Primitive
是 synthesis material，不是 runtime package dependency，因此目前不需要处理依赖图、版本
pinning 或级联 replay。

## 2. 必须区分的两轮历史实验

### 2.1 最早的 24-task 实验：mixed routing，不是 primitive-only

实验产物：

- [结果 Summary](../../evals/webarena/test_24_results/summary.json)
- [结果说明](../../evals/webarena/test_24_results/README.md)

这轮比较的是 scratch 和一个 **mixed router**。Treatment arm 的实际构成是：

| Route | Task 数 | 含义 |
|---|---:|---|
| `workflow:adapt` | 13 | 注入相关的完整 workflow，作为 adaptation prior。 |
| `primitive:adapt` | 3 | 注入站点 primitive。 |
| `primitive:skip` | 8 | Router 没有提供复用材料。 |

因此，这轮的 treatment 必须称为 `mixed routed`，不能称为 primitive-only。

| Arm | 正确数 | 准确率 | 平均 steps |
|---|---:|---:|---:|
| Scratch | 10/24 | 41.7% | 17.08 |
| Mixed routed | 10/24 | 41.7% | 12.83 |

配对结果是 3 wins、3 losses、7 both-correct、11 both-wrong。这轮说明复用材料和 routing
确实改变了 agent 行为，也降低了记录到的平均 steps；但由于大部分非 skip treatment 使用
的是完整 workflow，它不能隔离 primitive 的贡献。

### 2.2 上一版 primitive-only 24-task pilot

实验产物：

- [结果 Summary](../../evals/webarena/primitive_only_24_results/summary.json)
- [运行目录](../../evals/webarena/primitive_only_24_runs/)

这轮关闭 workflow retrieval，只比较 scratch 与 primitive retrieval。

| Arm | 正确数 | 准确率 | 平均 steps |
|---|---:|---:|---:|
| Scratch rerun | 14/24 | 58.3% | 15.79 |
| Primitive-only | 10/24 | 41.7% | 12.96 |

Primitive router 给出 17 个 `adapt`、2 个 `use` 和 5 个 `skip`。16 个最终脚本检测到了
primitive-source 代码。配对结果为 0 wins、4 losses、10 both-correct、10 both-wrong。
在这轮旧 integration protocol 下，primitive 没有提升准确率。

#### Scratch 对照组污染

14/24 不是有效的纯 scratch baseline。Scratch 与 primitive runs 被放在同一个 site-level
父目录，agent 又可以检查 workspace，因此 scratch trajectory 可以看见相邻的 primitive
artifact。

至少 task 57、179、189、362 暴露于 sibling primitive artifacts。Task 179 明确读取了
`task179_primitive.primitive_retrieval.json` 和相邻 primitive run，然后把 primitive ID、hash
以及 source marker 复制进自己的 `final_script.py`。

污染并不必然提高分数。Task 179 在更早的 scratch run 中正确，暴露后反而错误。其他 task
的变化还混有普通的模型重采样波动。因此，14/24 既不能解释成纯 scratch 成绩，也不能解释
成 primitive 带来的四分收益。正式 paired rerun 必须隔离两个 arm 的 workspace。

## 3. 为什么平均 steps 下降

Primitive-only pilot 中，总 steps 从 379 降到 311，减少了 68。但这 68 steps 完全没有来自
双方都正确的任务：

| 结果类别 | Pair 数 | Scratch steps | Primitive steps | 差值 |
|---|---:|---:|---:|---:|
| 双方都正确 | 10 | 141 | 141 | 0 |
| Scratch 正确、primitive 错误 | 4 | 82 | 54 | -28 |
| 双方都错误 | 10 | 156 | 116 | -40 |

也就是说，整体 step 降低全部来自 primitive 最终答错的任务。Primitive 经常通过直接提供
endpoint、selector 或 parser 缩短站点数据采集，但 agent 没有解决剩余语义或完整性缺口就
提前提交了答案。

代表性案例：

- Task 154，`14 -> 7`，由对变错：geocoding 和 OSRM 让 route acquisition 很快，但没有
  解决地点消歧和 destination selection。
- Task 243，`22 -> 11`，由对变错：admin 登录和 review 操作加速了采集，但 join、filter
  或 completeness 没有完整实现。
- Task 122，`30 -> 16`，由对变错：最终脚本虽然没有 incorporation primitive 函数，检索
  内容本身仍然产生 strategy anchoring。Agent 没有完成 scratch run 中更完整的验证就提交。
- Task 224，`28 -> 7`，双方都错：primitive 很快得到 car 和 foot durations，但遗漏了另一个
  evaluator 期望的交通方式。Scratch 找到了更多 modes，却输出了错误的 JSON shape。
- Task 205，`9 -> 19`，双方都对：primitive adaptation 给一个本来能直接从 commits 页面
  解决的简单任务增加了 API 和验证开销。

因此，效率必须与准确率一起报告，并使用 `steps conditional on correctness`。不能把所有
任务的 unconditional mean 当作效率收益，否则提前提交错误答案也会获得奖励。本轮 10 个
both-correct tasks 中，两臂平均 steps 恰好都是 14.1。

## 4. Primitive 造成错误的机制

现有证据不能推出“primitive 本身没用”。它暴露的是 abstraction boundary 和 integration
protocol 的问题：

1. Primitive 擅长提供**客观的站点采集能力**：登录、构造 endpoint、导航、稳定抽取和 typed
   parsing。
2. Cross-template task 的差异往往发生在采集之后：语义选择、完整遍历、record join、排序、
   聚合和输出 contract。
3. 旧 prompt 让检索材料过于 salient，partial primitive 容易 anchor 整个策略，被误当成完整
   solution plan。
4. Primitive 可以返回看似合理的数据，但不证明当前 task 的 acceptance conditions 已满足。
5. Provenance marker 只能说明代码出现过，不能证明函数真正执行或导致了最终答案。仅仅把
   retrieval material 暴露给 agent 就已经是一种 intervention。

新的核心原则是：**primitive 只能替换明确声明的局部 acquisition step，不能替换 scratch
方案中未覆盖的语义。** 如果字段缺失、pagination 不完整、发生异常或 acceptance check 失败，
必须执行该 step 原来的 scratch fallback，而不是直接输出 `NOT_FOUND_ERROR` 或提前提交。

## 5. 更新后的 Pipeline：相比上一版增加了什么

### 5.1 可审计的站点 Library 构建

- 输入是按网站分组、通过 gold gate 的 workflow scripts。
- 增量更新操作是 `ADD`、`UPDATE`、`NO_CHANGE/SKIP`。
- 每次更新记录 source workflow、template 和支持该能力的代码 evidence，便于审计。
- Evidence 可以支持把硬编码实例泛化成参数；不要求 generalized primitive 与 source code
  逐字节完全相同。
- 增量更新完成后，统一执行一次 `KEEP`、`MERGE`、`SPLIT` consolidation，同时修复重复、
  粒度和 feature 分类。
- 每个网站最终渲染成一个 package file：root site class 下组织多个 feature classes，例如
  `GitLabSite.auth`、`GitLabSite.issues`、`GitLabSite.commits`。
- 保存每批 update、pre-consolidation pool、consolidation proposal、validation、coverage、
  final index 和最终 package snapshot。

当前四站点 audited snapshot 从 17 个 gold-admitted workflows 构建：

| Site | Active primitives |
|---|---:|
| Shopping | 5 |
| GitLab | 8 |
| Shopping Admin | 4 |
| Map | 2 |

具体过程见：

- [Audited 建库说明](audited_cross_template_site_library_2026-08-10.md)
- [四站点 Library Snapshot](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/)

### 5.2 更明确的 Primitive Contract

- Primitive 尽量返回 typed objective facts，而不是无类型 DOM blob。
- `owns` 和 `does_not_own` 明确分开站点操作与 task semantics。
- Input/output contract 明确 consumer 能得到哪些字段。
- Router 必须列出 `remaining_gaps`，不能把 partial coverage 描述成完整覆盖。
- 禁止把 source task 的最终答案硬编码进 primitive，也禁止无 evidence 扩大 capability。

### 5.3 Scratch-first Local Patch Routing

旧 pilot 在 agent 形成方案前就暴露 primitive。更新后的流程先隐藏 library，生成 task-only
scratch plan；之后 retrieval 只能把 primitive 映射到具体 scratch step：

```text
task
  -> frozen scratch plan
  -> metadata retrieval + use/adapt/skip
  -> approved local patches: scratch_step -> primitive
  -> 保留未覆盖的 scratch steps
  -> 执行 patch，并检查 acceptance checks
  -> patch partial/失败时，运行该 step 的 scratch fallback
  -> 把通过的代码 vendor 到 standalone final_script.py
  -> evaluator
```

新版 prompt 明确规定：primitive 失败不代表网站事实不存在，也不能因为检索到了 primitive 就
重写或重排 frozen scratch plan 的其余部分。

### 5.4 Retrieval 行为

Retrieval 分两阶段：

1. 使用紧凑 metadata 排序：capability、ownership boundary、contracts、site/module、
   provenance 和 supported patterns。
2. 只对选中的 primitive 注入完整代码。

Router 的三个决策：

- `use`：primitive 覆盖所需站点操作；task semantics 和 formatting 仍由当前 workflow 负责。
- `adapt`：primitive 能替换一个或多个局部步骤，但存在明确的 remaining gaps。
- `skip`：检索材料不能实质推进 scratch plan。

Workflow retrieval 是单独的 ablation。任何被报告为 primitive-only 的实验都不能静默混入
workflow adaptation。

## 6. 完整的 Build-to-Evaluation Workflow

```text
按网站划分的 gold-admitted train workflows
  -> batch incremental updater
       ADD / UPDATE / NO_CHANGE
       记录每个 workflow 的贡献
       保存 batch snapshots
  -> pre-consolidation primitive pool
  -> consolidate + organize
       KEEP / MERGE / SPLIT
       验证 workflow coverage 和 contracts
       渲染一个 object-oriented site package
  -> freeze library + manifest
  -> held-out cross-template task
       retrieval 前生成 scratch-only plan
       从同网站 library 检索 primitive metadata
       决定 use / adapt / skip
       获取选中 primitive 的完整代码
       声明 local patches、remaining gaps、acceptance checks
       将通过的 methods vendor 进 standalone workflow
       保留 scratch fallbacks
  -> WebArena evaluator
  -> paired report
       accuracy first
       wins / losses / both-correct / both-wrong
       steps conditional on correctness
       route 与 incorporation diagnostics
```

正式实验中，scratch 和 primitive arms 必须运行在彼此不可访问的 workspace。当前目录约定仍
允许 sibling visibility，因此“trajectory 中暂时没发现读取”不足以构成严格无污染证明。重新
聚合前应物理隔离两个 arm，并审计 trajectory 的文件访问。

## 7. 2026-08-11 干净对照结果

我们在独立的 `/tmp` 实验根目录重新运行了相同 24 个 held-out tasks 的 scratch arm。该目录
没有生成 primitive arm；审计全部 24 条 trajectory 后，没有发现读取 primitive retrieval、
site library 或历史实验结果的行为。

| Arm | 正确数 | 准确率 | 平均 Webwright steps |
|---|---:|---:|---:|
| Clean scratch | 11/24 | 45.8% | 9.58 |
| Updated primitive | 13/24 | 54.2% | 8.50 |

配对结果为 3 wins、1 loss、10 both-correct、10 both-wrong。但归因需要进一步区分：

- Task 122、154 是 `adapt` 路由下的 primitive-exposed wins。
- Task 113 是 `adapt` 路由下的 primitive-exposed loss。
- Task 3 的 primitive arm 实际决策为 `skip`，没有注入 primitive，因此该 win 属于独立
  重采样差异，不能归因于 primitive。

所以完整系统结果是 `13/24 vs 11/24`，而直接与 primitive exposure 相关的变化是
`2 wins / 1 loss`。样本仍然较小，这不是统计显著性声明。

在 10 个双方都正确的任务上，scratch 平均 7.6 steps，primitive 平均 8.0 steps。原本能做对
的任务已经很短，primitive 没有进一步提速。并且 frozen-plan/retrieval 生成发生在 Webwright
step 计数之外，因此 8.50 不能解释成端到端成本优势。

完整记录见 [clean paired results](../../evals/webarena/formal_32_24_audited_v4_clean_results/)。

## 8. 当前结论与下一次测量

最早的结果只能说明 mixed reuse 改变了策略，不能隔离 primitive。上一版 primitive-only pilot
说明旧 pipeline 可以检索并 incorporation primitive，但结果是 0 wins、4 losses，而且 scratch
对照组受到污染。这两轮都不是最终 efficacy number。

更新后的 pipeline 测试一个更窄、也更可证伪的假设：正确的站点 primitive 是否能安全替换
特定 acquisition steps，同时保留 consumer 自己的 scratch semantics。当前干净 paired run
提供了初步正信号，但仍需要扩大样本或重复 seeds 验证稳定性。

当前准确状态是：

- Library construction 和 retrieval mechanism 已实现并经过测试。
- Primitive coverage、来源和每个 workflow 的贡献可审计。
- 旧 integration protocol 下的 accuracy 结果为负。
- 更新后的 integration protocol 在 24-task retrieval-only eval 上为 13/24，对照为 11/24。
- 可直接归因于 primitive exposure 的变化为 2 wins、1 loss；下一步重点是修复 task 113
  regression，并验证收益是否能在更大样本或重复运行中保持。

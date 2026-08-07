# Mentor Sync：WebArena 跨模板 Primitive 实验

状态：**临时快照，2026-08-07**。32 train / 24 test 实验在记录本快照时仍有最后的
Shopping Admin 配对尚未结束，以下数字不是最终结果。

## 一分钟总结

我们正在测试：skill library 能否在同一个网站的不同 task template 之间，复用粒度更小的
站点能力。

MVP 将 primitive 定义为**代码合成材料**，而不是运行时依赖。Retriever 把相关代码提供给
agent，最终保存的 workflow 仍然是完整、独立的脚本。这避免了版本 pinning、依赖 DAG、
primitive 更新导致历史 workflow 级联失效，以及大规模 replay。

本轮实验为四个网站分别建立独立 library：

- Shopping
- GitLab
- Shopping Admin
- Map

使用固定 seed 在 template 层随机划分，每个 template 只随机取一个 instance，train/test
template 严格不重叠：

- 32 个 train tasks：每站 8 个不同 templates；
- 24 个 test tasks：每站 6 个 unseen templates；
- test 运行 scratch 与 workflow-first routed 两个配对 arm；
- 仅使用 retrieve tasks；
- 不按照任务难度、scratch 成败或 primitive overlap 人工挑选；
- seed：`20260807`。

在当前 22/24 pairs 的临时快照中：

- Scratch：10/22，45.5%；
- Routed：10/22，45.5%；
- 3 Win / 3 Loss / 7 both-correct / 9 both-wrong；
- Scratch 平均 17.36 agent steps；
- Routed 平均 13.14 agent steps，下降约 24.3%。

这里的 step 只统计 agent trajectory 中的 API calls，没有计入 router 自身的一次 LLM 调用、
retrieval token 和注入 token，因此暂时不能直接等价为端到端成本下降。

## 当前实现

已经推送的基础实现位于 `cross-task-primitives` 分支的 commit `421eb94`。

### 1. 可复现的随机划分

Sampler 使用 seed 和 SHA-256 对 template 排序，结果不受 dataset 输入顺序影响。划分发生在
template 层，而不是 task ID 层，因此能够严格保证 train/test template 不重叠。

### 2. Gold admission

只有 WebArena evaluator 得分为 1 的 train workflow 才能进入 library 构建。随机选中的失败
任务不会被替换，也不会贡献 primitive 或 workflow。

### 3. 每个网站一个独立 library

实验单位是 cross-template within the same website：

```text
Shopping train → Shopping library → Shopping test
GitLab train → GitLab library → GitLab test
Admin train → Admin library → Admin test
Map train → Map library → Map test
```

四个 library 共享 schema、updater 和 retriever，但不共享内容。结构上禁止跨站 retrieval。

### 4. Primitive updater

Updater 支持以下元操作：

- `ADD`
- `MODIFY`
- `SPLIT`
- `ARCHIVE`
- `NO_CHANGE`

Admission gate 检查：

- Python 语法；
- entrypoint 与 signature；
- primitive 文件自包含，不引用其他 catalog primitive；
- source workflow/template provenance；
- source answer 泄漏；
- primitive ID 与 site namespace。

本轮正式 library 中没有手写 primitive。

### 5. Workflow-first router

当前 routing 顺序：

```text
精确/可直接运行的 workflow
    ↓ 没有
相关 workflow：adapt 或 skip
    ↓ skip
primitive metadata retrieval：use / adapt / skip
    ↓ skip
scratch
```

Retriever 首先只读取 primitive metadata；只有决定 `use/adapt` 后才获取完整代码，避免把所有
候选函数都注入 prompt。

### 6. Vendoring / Copy-on-use

Workflow 保存完整 standalone code，不在运行时 import catalog primitive。因此：

- primitive 更新不会破坏历史 workflow；
- MVP 不需要 dependency graph；
- 不需要版本求解或 pinning；
- 不需要因为 primitive 修改而级联 replay 所有 consumer。

Shared imports、executable primitives、版本依赖和 replay gate 保留到 release 设计。

### 7. 实验执行与 instrumentation

当前 harness 支持：

- 每网站独立并发 lane；
- 可恢复运行；
- 进程组级 timeout 清理；
- evaluator commit 与 null-fix provenance；
- frozen-library hash 校验；
- scratch/routed 配对聚合；
- route stage、decision、reason、remaining gap、workflow ID 和 primitive provenance 记录。

主要实现路径：

- `evals/webarena/sample_cross_task_split.py`
- `evals/webarena/run_cross_task_plan.py`
- `evals/webarena/cross_task_eval.py`
- `evals/webarena/build_generated_primitives.py`
- `evals/webarena/aggregate_cross_task_results.py`
- `src/webwright/skill_factory/primitive_catalog.py`
- `src/webwright/skill_factory/primitive_update.py`
- `src/webwright/skill_factory/primitive_retrieve.py`
- `src/webwright/skill_factory/route.py`

## Library 构建结果

32 个随机 train tasks 全部完成，没有 infrastructure failure：

| 网站 | 随机选中 | Gold-admitted | Workflow priors | Primitives |
|---|---:|---:|---:|---:|
| Shopping | 8 | 4 | 4 | 2 |
| GitLab | 8 | 7 | 7 | 1 |
| Shopping Admin | 8 | 3 | 3 | 2 |
| Map | 8 | 3 | 2 | 2 |
| **总计** | **32** | **17** | **16** | **7** |

Map 的 3 个 admitted records 在 workflow grouping/distillation 后形成 2 个 workflow priors；三个
source records 都保留在 provenance 中。四个 library 在 reset 和 test 之前已经冻结并记录 hash。

## 临时测试结果：22/24 pairs

| 网站 | 完成 pairs | Scratch 正确 | Routed 正确 | Win | Loss | Scratch 平均 steps | Routed 平均 steps |
|---|---:|---:|---:|---:|---:|---:|---:|
| Shopping | 6/6 | 3 | 4 | 1 | 0 | 15.00 | 12.33 |
| GitLab | 6/6 | 3 | 2 | 1 | 2 | 13.83 | 12.50 |
| Shopping Admin | 4/6 | 2 | 3 | 1 | 0 | 25.00 | 17.50 |
| Map | 6/6 | 2 | 1 | 0 | 1 | 18.17 | 11.67 |
| **当前总计** | **22/24** | **10** | **10** | **3** | **3** | **17.36** | **13.14** |

已完成 pairs 中，router 做出 15 次 `adapt` 和 7 次 `skip`。

### 当前解释

- 新的随机 test 不再被 ceiling 主导：22 个 pairs 中有 9 个 both-wrong。此前 18/12 pipeline
  pilot 中 scratch 已通过 10/12，几乎没有观察收益的空间。
- Reuse 确实改变了行为：目前同时产生 3 个 Win 和 3 个 Loss，而不仅仅是添加 provenance
  marker。
- 收益具有明显的网站异质性：Shopping 和 Admin 暂时为正，GitLab 和 Map 暂时为负。
- Routed 的 agent trajectory 更短，但端到端成本还缺少 router token、注入 token、LLM 调用和
  wall-clock instrumentation。
- 当前结果支持继续研究 contract 和 routing quality，不支持宣称准确率提升。

## 目前得到的设计原则

### 1. Primitive contract 应拥有稳定的站点语义

站点特有的输出格式、单位和稳定解析规则应该由 primitive 统一处理。Task-specific filtering、
aggregation、formatting 和主观语义判断仍由 workflow/task layer 完成。

### 2. Retrieval exposure 本身就是 intervention

代码中存在 provenance marker，甚至复制了一个函数，都不能证明 primitive 真正被执行。检索到
的材料可能通过 strategy anchoring 改变 agent 行为，因此必须区分：

- retrieved；
- incorporated；
- execution-reached；
- 最终行为变化。

### 3. `skip` 是核心能力

不是所有相关材料都值得注入。错误的 `adapt` 可能将 agent 锚定到不适合当前 task 的策略。
当前 Loss 需要按 case 区分：primitive 内容错误、workflow contract 不完整、routing 错误，还是
普通运行方差。

### 4. 每站独立，机制统一

统一的是 package schema、updater、retriever 和 eval protocol；library 内容与冻结边界必须按
website 独立。

### 5. MVP 暂不引入运行时依赖

Vendoring 是当前最小、可维护的设计点。只有观察到 copy-on-use 无法支持的真实需求后，才考虑
shared imports、更多层级或 DAG。

## 正在开发但尚未进入 frozen condition 的内容

当前 working tree 正在探索 evidence-gated updater：

- 每个 primitive proposal 必须为每个 source workflow 引用一段连续、逐字一致的能力代码；
- quote 必须是 capability-specific implementation，不能只是 import、login、navigation 或通用
  page text；
- 独立 judge 检查语义支持和与已有 primitive 的重复；
- 一个 source 的候选标记为 `single_source`，两个及以上独立 templates 才标记为 `shared`；
- MODIFY 合并并保留已有 verified provenance。

这些改动和对应的 experimental library variants 尚未进入 commit `421eb94`，也不是当前正式
frozen test 的实验条件。

## Artifact 路径

- 总 split：`evals/webarena/splits_32_24/manifest.json`
- 各站 split：`evals/webarena/splits_32_24/{shopping,gitlab,shopping_admin,map}.json`
- Train results：`evals/webarena/train_32_results/<site>/`
- Gold-admitted manifests：`evals/webarena/train_32_admitted/`
- Frozen site libraries：`evals/webarena/site_libraries_32_24/<site>/`
- Test results：`evals/webarena/test_24_results/<site>/`
- 完整 run artifacts：`evals/webarena/{train_32_runs,test_24_runs}/<site>/`
- 旧 18/12 robustness pilot：`evals/webarena/test_12_results/README.md`
- MVP 设计：`docs/skill_factory/cross_task_primitive_mvp.md`
- Release 设计：`docs/skill_factory/cross_task_primitive_release.md`
- 设计决策：`docs/skill_factory/cross_task_primitive_decisions.md`
- Human review queue：`docs/skill_factory/cross_task_primitive_review_queue.md`

## Mentor Sync 建议讨论的问题

1. 论文的主张应该是随机分布上的整体准确率，还是 capability-conditional reuse，并将随机 split
   作为 robustness result？
2. 如果最终准确率打平、但 agent trajectory 明显缩短，在补齐 router token 和 wall-clock 后，
   是否足以支持 cost-aware routing 方向？
3. `single_source` primitive 应该作为较低置信度的 synthesis hint 暴露，还是必须等第二个独立
   template 确认后才能进入 active retrieval surface？
4. 下一轮是否应该拆分 ablation：scratch、raw workflow、distilled workflow、primitive-only、
   full workflow-first routing？

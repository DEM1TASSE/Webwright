# Primitive Class + Single-Source Updater：当前设计与进度

日期：2026-08-08
分支：`cross-task-primitives`

## 1. 当前目标

实现并验证下面这条最小 pipeline：

```text
gold-admitted workflow
  → 提取站点相关 primitive method
  → single-source evidence gate
  → 增量更新一个 website primitive class
  → metadata-only retrieve
  → 注入选中 method 的完整 class 代码
  → 生成 standalone workflow
```

本轮只研究 primitive，不引入 component，也不允许 cross-template workflow adaptation。

## 2. 已确定的语义

### 2.1 一个网站一个真实 class

期望生成的产物是实际可解析的 Python class，而不是 catalog wrapper 或散装函数：

```python
class GitLabPrimitives:
    @staticmethod
    def fetch_repository_commits(...):
        ...

    @staticmethod
    def parse_project_members(...):
        ...
```

对应四个站点：

- `ShoppingPrimitives`
- `GitLabPrimitives`
- `ShoppingAdminPrimitives`
- `MapPrimitives`

class 是 library 的组织、更新和检索边界。最终 workflow 仍然 vendor 选中的实现，不能在运行时 import primitive library。

### 2.2 Single-source 是合法的初始 method

不再要求一个 primitive 必须先由两个不同 template 共同支持。

```text
一个 gold workflow 直接实现稳定的站点操作
  → ADD single_source method

后续 workflow 提供相同或相近证据
  → MODIFY 已有 method、扩展 contract 和 provenance
  → 来源覆盖多个 template 后 grade 升为 shared
```

`single_source/shared` 是证据强度，不是 admission 的二元门槛。

### 2.3 最小更新操作

当前 updater 只允许：

- `ADD`
- `MODIFY`
- `NO_CHANGE`

暂不允许 `ARCHIVE`、`SPLIT`、`MERGE`、`MOVE`，也不维护 component。

### 2.4 Primitive-only routing

本轮 cross-template 路由为：

```text
primitive metadata decision
  ├─ use/adapt → 获取并注入选中 methods 的完整 class 代码
  └─ skip      → scratch
```

不再把语义相关的 workflow 当 adaptation prior。正式系统以后可以保留“精确 workflow match 直接运行”，但 cross-template primitive 实验不使用 workflow-adapt。

## 3. GitLab 之前为什么没有 primitive

`site_libraries_32_24_evidence_gated_v4` 使用了错误的强约束：只有同一 capability 在至少两个不同 template 中都有 capability-specific code，才允许创建 primitive。

GitLab 的 gold workflows 分别覆盖 project list、contributors、issues、commits、members、project search 和 local git history。它们包含多个有效的站点操作，但同一操作在两个 template 中的直接重叠很少，因此 updater 将所有轮次判为 `NO_CHANGE`，最终 `active_primitives=[]`。

这不是 GitLab 不可访问，也不是没有可提取操作，而是 admission granularity 错误。

## 4. 当前代码修改

### 4.1 Class 物化

文件：`src/webwright/skill_factory/primitive_catalog.py`

已增加：

- `site_class_name(site)`：生成稳定 class 名称；
- `render_site_primitive_class(site, primitives)`：把独立 primitive modules 编译为一个真实 class；
- private helper 按 public method 加名前缀，防止不同 method 中同名 `_normalize` 相互覆盖；
- `PrimitiveCatalog.materialize_site_class()`；
- 每次 `upsert` 后自动更新 `.primitives/<site>/primitives.py`。

磁盘结构预期为：

```text
.primitives/<site>/
├── catalog.json
├── primitives.py       # 一个真实的 site class
└── code/               # 每个 method 的独立 provenance/source module
    └── <method>.py
```

### 4.2 Retriever

文件：`src/webwright/skill_factory/primitive_retrieve.py`

已改为：

1. decision prompt 只看 method metadata，不提前暴露代码；
2. 选中后获取完整实现；
3. 注入内容以真实 `SitePrimitives` class 展示；
4. 未选中的 method 不进入 prompt。

### 4.3 Updater

文件：`src/webwright/skill_factory/primitive_update.py`

当前 prompt 和 evidence judge 已明确：

- 一个真实 source workflow 足以创建 `single_source` method；
- 不得仅因缺少第二个 template 而拒绝；
- 每个引用 workflow 必须提供连续、可定位的 capability-specific code quote；
- generic browser/HTTP setup、同网站、相似 goal 不能作为证据；
- 与 active method 重复时应 `MODIFY` 或 `NO_CHANGE`，不能重复 `ADD`。

### 4.4 Eval routing

文件：`evals/webarena/cross_task_eval.py`

`prepare_routed_hint()` 已设置 `cross_template_workflow_first=False`，即 cross-template treatment 不再走 workflow adaptation。

## 5. 已完成测试

运行范围：

```text
test_primitive_catalog.py
test_primitive_retrieve.py
test_primitive_update.py
test_route.py
test_cross_task_eval.py
test_run_cross_task_plan.py
```

最近一次结果：

```text
72 passed in 0.34s
```

覆盖内容包括：

- class 文件可解析；
- `GitLabPrimitives` 含真实 static methods；
- 不同 method 的同名 private helper 被隔离；
- retrieval metadata 不包含代码；
- injection 包含选中 class method，不包含未选中 method；
- single-source `ADD` 得到 `grade=single_source`；
- 多 template provenance 得到 `grade=shared`；
- cross-template eval 使用 primitive-only policy；
- `SPLIT/ARCHIVE` 在最小协议中被拒绝。

## 6. Fresh rebuild 状态

### 输入

- gold workflow manifest：`evals/webarena/train_32_admitted/by_site.json`
- 共 17 个 gold-admitted workflows：
  - Shopping：4
  - GitLab：7
  - Shopping Admin：3
  - Map：3
- dataset：`/home/t-demiwang/project/Code-Web-Agent/webarena_test/dataset/webarena-verified.json`

### 重要约束

Fresh build 从空 library 开始调用 updater。旧 `single_source_v2` 只用于诊断之前的规则问题，不能复制、迁移或作为新 library 的输入。

### 尝试 1

路径：`evals/webarena/site_libraries_32_24_primitive_class_v1/`

结果：中途停止，仅生成 GitLab 2 个 methods，没有最终 build report。这是无效半成品，不能用于评测。

### 尝试 2

路径：`evals/webarena/site_libraries_32_24_primitive_class_v2/`

结果：中途停止，仅生成 GitLab 4 个 methods，没有最终 build report。这同样是无效半成品，不能用于评测。

当前没有后台 build 进程运行。两次目录都必须视为 debug artifacts，而不是正式 library。

## 7. 正式产物验收规则

新的 fresh build 只有同时满足以下条件才算成功：

1. build report 存在且完整记录 17 个 source workflows；
2. 四个网站都生成 `.primitives/<site>/primitives.py`；
3. 每个文件只包含对应网站的一个 public primitive class；
4. class 中每个 public method 都能映射到 catalog 中唯一的 primitive id；
5. 每个 active method 至少有一个 gold workflow 和通过验证的 code evidence；
6. 单来源 method 标记 `single_source`，不能因为没有第二来源被删除；
7. method 之间没有代码调用依赖；`requires/provides` 只表示状态 contract；
8. class 文件可以 `compile`，且最小 smoke invocation 能证明 private helper 名称不会冲突；
9. 不允许读取或复制旧 primitive library；
10. 通过以上静态验收后，才能进入 primitive-only WebArena eval。

## 8. 下一步

1. 给 build 脚本增加逐 workflow checkpoint/error log，避免 API 或 class materialization 错误只留下无报告半成品；
2. 从第三个全新空目录重新运行 17-workflow updater；
3. 自动生成 class/catalog/evidence 审计报告；
4. 对不符合规则的 method 定位为 proposer、evidence judge 或 class compiler 问题并修复；
5. 通过验收后，先跑每站少量 primitive-only smoke tasks；
6. smoke 稳定后再运行完整 paired test。

## 9. 当前未完成项

- Fresh 四站 class library 尚未成功生成；
- 两次 build 中止原因尚未被持久化，需先补 checkpoint/error logging；
- 尚未运行新的 primitive-only WebArena E2E；
- 当前修改尚未 commit/push；
- 工作区还有此前实验产生的大量未提交 artifacts，提交时必须只选择本轮代码、测试、文档和最终有效报告，不能误提交旧 run 目录或失败的 `v1/v2` 半成品。

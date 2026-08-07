# Cross-Task Primitive Release：Executable、Gates、Dependencies 与 Replay

> **Future full-system design.** 本文只在
> [`cross_task_primitive_mvp.md`](cross_task_primitive_mvp.md) 通过预注册 WebArena
> gates 后实施。MVP 证明 primitive code 作为 synthesis material 是否有效；本阶段再把
> primitive 升级为可执行、可共享和可维护的软件包。

## 1. 进入条件

开始完整版前，MVP 至少满足：

1. Oracle pilot 达到预注册 GO 条件；
2. retrieved primitives 在严格 cross-template WebArena 上显示稳定 downstream utility；
3. agent 实际 incorporated primitive code，而不只是 retrieved；
4. catalog growth 和 false abstraction 没有快速失控；
5. 至少两个任务族显示相同方向。

否则 shared imports 只会增加工程复杂度。

## 2. 从 MVP 到 Release

MVP：

```text
primitive code
→ retrieve
→ copy/adapt
→ standalone workflow
```

Release：

```text
verified primitive package
→ stable import
→ dependency manifest
→ selective validation
→ safe release / rollback
```

完整版目标：

- primitive 可独立调用；
- public contract 明确；
- workflow 可选择 vendoring 或 shared import；
- 更新不隐式改变已有消费者；
- breaking change 可迁移、可回滚；
- replay 成本与 affected set 相关，而不是与全库规模相关。

## 3. Artifact Model

```text
library/
├── site_packages/
│   └── gitlab/
│       ├── releases/
│       │   ├── <content_hash_1>/
│       │   │   ├── ops.py
│       │   │   ├── contracts.json
│       │   │   └── verification.json
│       │   └── <content_hash_2>/
│       └── active.json
│
└── workflows/
    └── commits_by_user_date/
        ├── skill.py
        ├── dependencies.json
        └── replays.json
```

优先使用 content-addressed immutable releases，而不是手工维护大量 `@1/@2`。人类可读
版本可以以后增加。

## 4. Public Contract

```yaml
id: gitlab/open_repo
release: sha256:...

inputs:
  page: PlaywrightPage
  repo: string

output:
  type: RepoContext

requires:
  - authenticated_session

provides:
  - repo_context

side_effects:
  - browser_navigation

errors:
  - RepoNotFound
  - AuthenticationRequired
```

必须区分：

- code dependency：Python import/call；
- environment precondition：`requires/provides`；
- data contract：inputs/output；
- side effect：导航、mutation、外部写入。

## 5. Verification Grades

### Reference

- 来源 workflows 通过 gold；
- static parse/compile；
- 可作 synthesis material；
- 不允许 shared runtime import。

### Contract-tested

- 独立 invocation 可运行；
- input/output schema 通过；
- `requires/provides` 状态被观察；
- 允许 experimental import。

### Replay-verified

- source-derived cases 通过；
- representative consumer workflows 通过；
- mutation primitive 通过 benchmark/network evaluator；
- 允许 stable import。

Retriever 和 route 不得把 reference primitive 当作 standalone executable。

## 6. Release Gates

### Gate 1：Provenance

- source tasks 通过 gold；
- 至少两个不同 templates，或明确人工审核例外；
- 记录 source runs、环境和数据版本。

### Gate 2：Static Integrity

- AST parse/compile；
- imports 可解析；
- 无硬编码答案；
- signature 与 contract 一致；
- dependency closure 完整；
- 无循环 public dependency。

### Gate 3：Contract Execution

- 在声明的初始状态运行；
- 验证 output schema；
- 验证 provides state；
- 验证 error/timeout；
- 多次运行测基本稳定性。

### Gate 4：Source Cases

- 执行 source-derived cases；
- changing answers 使用 shape/property/current gold，而不是过期 strict answer；
- mutation 使用 WebArena network/state evaluator。

### Gate 5：Consumer Canary

- 覆盖不同 start URL、auth state、result shape、retrieve/mutate；
- candidate 不自动替换旧 release；
- canary 通过后才允许新 workflows 采用。

### Gate 6：Promotion

- validation utility 不下降；
- regression failures 在预设阈值内；
- 记录 rollback target。

## 7. Dependencies

Workflow manifest：

```json
{
  "workflow_id": "commits_by_user_date",
  "dependencies": [
    {
      "primitive_id": "gitlab/open_repo",
      "release": "sha256:abc..."
    },
    {
      "primitive_id": "gitlab/list_commits",
      "release": "sha256:def..."
    }
  ]
}
```

Workflow pin immutable release。`active.json` 只决定新 workflow 的默认选择，不改变历史
workflow。

Reverse dependency index 从 manifests 自动生成，不作为手工 source of truth。

完整版第一阶段仍限制为：

```text
site primitive → workflow
```

Public primitive 暂不依赖 public primitive；模块内部可以有 private helpers。只有真实需求
证明两层不足时，才增加 public dependency graph。

## 8. Update Operations

### ADD

创建 immutable release，通过适用 gates 后加入 active catalog。

### FIX / EXTEND

创建新的 content-addressed release：

```text
old release remains
new workflows default to candidate after promotion
old workflows remain pinned
```

### SPLIT

```text
A → B + C
```

- 保留 A 给历史 consumers；
- B/C 分别通过 gates；
- active retrieval 可以隐藏 A；
- 不自动迁移旧 workflows。

### MERGE

只在重复 primitive 已产生实际 retrieval 噪声时实施。新 merged release 不删除旧 releases。

### DEPRECATE

- active catalog 不再推荐；
- pinned consumers 仍可运行；
- 无消费者后再归档。

## 9. Selective Replay

不对每次更新全库 replay。

| 变化 | 验证范围 |
|---|---|
| private helper，public contract 不变 | primitive contract + source cases |
| compatible new release | contract + source cases + consumer canary |
| workflow migration | 只 replay 被迁移 workflows |
| high fan-out / breaking change | coverage set → staged canary → larger affected suite |

Coverage-based consumers 按以下维度选择：

- template；
- start URL；
- authentication/permission；
- empty/single/multi-page result；
- retrieve/mutate；
- historical failure mode。

随机抽样不能作为高风险发布的唯一 gate。

## 10. Replay Suite Growth

分开保存：

```text
provenance archive:
  所有 source run 记录，不在每次更新执行

active regression suite:
  每个 coverage bucket 的代表 cases

periodic full audit:
  release/nightly 低频执行更大集合
```

新增 case 只有增加新的环境、参数、页面状态或 failure-mode coverage 时才进入 active suite。

## 11. Migration

Migration 是显式 job，不是 primitive update 的隐式副作用：

```text
select consumers
→ rewrite imports/manifest
→ replay selected workflows
→ publish new workflow artifact
→ retain rollback copy
```

优先迁移高频、已 stale 或能从关键修复获益的 workflows。低价值 workflow 可以继续
vendoring 或 pin 旧 release。

## 12. Runtime Routing

```text
exact verified workflow
→ run pinned dependencies

same-template workflow with unsupported pattern
→ adapt or repair the workflow first

no exact workflow
→ retrieve active executable primitives
→ compose/adapt

reference primitive
→ synthesis material only

no useful primitive
→ scratch
```

成功后仍遵循：

```text
same template → update workflow
new template  → add workflow
cross-template comparison → propose primitive update
```

Budget-aware `use/skip` 可以独立增加，不是 executable release 的前置条件。

## 13. Release Evaluation

除 MVP 指标外，增加：

- primitive contract/source-case pass rate；
- consumer canary pass rate；
- regression failures per update；
- affected workflows per release；
- replay wall time；
- migration success/rollback rate；
- dependency fan-out；
- stale pinned workflows；
- vendored vs imported performance；
- direct primitive execution coverage；
- active 和 archived release 数量。

关键对照：

```text
Vendored MVP workflow
vs
Shared-import workflow pinned to immutable release
```

必须证明 shared imports 的维护、生成或执行收益值得其 dependency/replay 成本。

## 14. Rollout

### R0：Shadow

Primitive 运行 contract/source cases，但不被 workflow import；与 vendored implementation
比较输出。

### R1：Experimental Imports

少量 canary workflows、immutable pin、快速 rollback。

### R2：Stable Imports

Replay-verified grade；新 workflows 可以默认 import。

### R3：Selective Migration

只迁移高价值 workflows；其他历史 workflow 保持 vendored。

### R4：Optional Dependency Expansion

只有两层 public dependency 阻碍真实任务时，才研究 public primitive composition、deeper
dependency graph 和 graph-aware affected replay。

## 15. Release 成功标准

1. executable primitives 独立通过 contract/source cases；
2. shared imports 不降低 WebArena cross-template success；
3. update 不隐式改变 pinned historical workflows；
4. selective replay 能捕获真实 regression；
5. replay 时间由 active affected set 控制；
6. rollback 能恢复旧 release；
7. shared imports 相比 vendoring产生可测收益。

如果第 7 项不成立，vendoring 可以继续作为正式架构，而不必升级 shared imports。

# WebArena Primitive V12 Pipeline Review

日期：2026-08-21

## 结论

V12 是当前已经完成大规模配对实验、且结果最好的 direct primitive pipeline。它适合复现原有的单站点 Retrieve/Navigate T2 实验，但不能不加修改地用于新的 399-task full set：当前执行入口不支持 Multi，Mutate 的终止输出协议也尚未闭合。

V12 的结果来自 V11 生成的 audited candidate library，而不是一套独立的 V12 library。代码历史没有单独的 V12 source checkpoint；本分支保存的是目前完整的生成、检索、评测和测试实现，并明确记录这一区别。

## 已有结果

原 T2 split：156 个 template-disjoint tasks，57 个 held-out templates。

| Arm | Success | Mean agent steps |
|---|---:|---:|
| Scratch | 93/156 = 59.6% | 13.20 |
| Primitive | 100/156 = 64.1% | 11.90 |
| Delta | +7 tasks / +4.5 pp | -9.8% |

Primitive code 实际曝光的 25 个配对中：7 Win、2 Loss、12 both-correct、4 both-wrong，平均减少 6.6 steps。按 route decision：

- `use`：17 tasks，6 Win / 1 Loss，平均减少 7.59 steps；
- `adapt`：8 tasks，1 Win / 1 Loss，平均减少 4.50 steps；
- `skip`：131 tasks。该部分仍有 13 Win / 11 Loss，说明总体差值包含采样方差，严格 attributed net gain 是 exposed subset 的 +5。

机器可读结果见 `reuse_split_v1_eval_results_v12_mixed_paired/summary.json`。

## Pipeline

```text
gold-admitted standalone workflows
        |
        v
per-workflow capability extraction (parallel)
        |
        v
independent batches, default size 4 (parallel)
  ADD / UPDATE / SKIP against a frozen empty catalog
        |
        v
site-level consolidation (serial)
  KEEP / MERGE / SPLIT + feature organization
        |
        v
Site package
  Site class -> feature components -> public primitives
        |
        v
metadata-first retrieval
  use / adapt / skip + contract verification
        |
        v
selected full method code is vendored into a standalone workflow
        |
        v
official WebArena evaluator + paired scratch comparison
```

Primitive 是 synthesis material，不是 runtime dependency。历史 workflow 不 import library；library 更新不会改变已经生成的 standalone workflow。

## V11 library snapshot

V12 本地消费的原始包位于 `primitive_rt_v1_library_v11_all/`。本分支提交的可公开版本位于
`primitive_rt_v1_library_v11_public/`：

| Site | Source workflows | Final primitives |
|---|---:|---:|
| GitLab | 10 | 8 |
| Map | 16 | 3 |
| Shopping | 10 | 8 |
| Shopping Admin | 15 | 11 |
| Reddit | 0 | 0 |

合计 51 个 source workflows、30 个 candidate primitives。所有产物均标记为 `candidate / approved=false`；Map 做过迭代 behavior smoke，其他站点主要经过生成时的静态和 LLM gate。

原始 atomic audit 快照没有提交到公共分支，因为它保留了 source workflow 全文，其中包含测试账号凭据和内部部署主机名。公开版本保留完全相同的 30 个 method bodies、runtime contracts、feature organization 和 reviews，仅从 index 删除 source evidence/attribution；30 个 method-code hashes 与实际评测版本逐一相同。

## 必须在 399-task full run 前解决的问题

### 1. Multi-site execution

当前 split validator 要求每条任务只有一个 site，执行时也直接读取 `task["sites"][0]`。新 split 的 25 个 Multi test tasks 不能由当前入口正确执行。Multi 应按任务涉及的网站检索多个 site packages，然后由同一个 workflow composer 组合；不应生成 `_multi` 网站包。

### 2. Mutate task interface

当前官方任务只有 Navigate 的独立输出协议；其他类型会落到 Retrieve 协议。Mutate prompt 因而要求 `task_type=RETRIEVE`，完成检测却期待 `MUTATE`，会造成 timeout/incomplete。需要增加官方 Mutate artifact/termination 协议。

Effectful primitive 还需要机器可检查的 typed receipt，区分 success、no-op 和 failure，并声明 effect/postcondition。第一轮可以让 Mutate 使用安全的 read/navigation primitives，同时禁止未闭合的 effectful primitive 进入 active surface。

### 3. Build identity and safe resume

现有 build wrapper 看到旧 `final_candidate/index.json` 就可能直接复用，不核对 manifest、workflow IDs/code hashes、dataset、model 或 prompt。内部 batch resume 也只检查 build mode、batch size 和 seed。

正式建库必须使用全新输出目录；随后应加入完整 build fingerprint，禁止新 split 静默复用旧库。

### 4. Consolidation scaling

当前每站点将所有 batch candidates 一次性送入一个全局 consolidation。51 个 source workflows 时，单站 consolidation input 已约 18k--25k rough tokens；扩展到数百 workflows 后可能超过稳定上下文并丢 coverage。

建议改成：

```text
parallel induction
-> deterministic coarse feature grouping
-> feature-local consolidation
-> lightweight site-level organize/dominance pass
```

每一层仍保存 candidate keys、operations 和 source attribution。

## 现有 primitive contract 风险

- GitLab `list_repository_contributors` 没有显式分页，不能支持 all/top/max population reducer。
- Shopping orders 存在多个重叠 acquisition；部分 list 输出不能提供 `order_id`，无法闭合 list-to-detail dataflow。
- Shopping Admin review detail 声称 complete，但缺字段时可返回默认 `rating=0`、空状态或整个 Product block。
- Shopping Admin all-review count 同时写入 `pending_review_count`，字段语义错误。
- Map search 是 ranked、query-scoped partial acquisition；empty 不能证明 absence。文本 routing 必须验证 resolved endpoint identity，而不能只检查 duration 是否存在。

这些风险应通过通用 contract verifier 处理，不应写 task/site 特例。Verifier 只检查结构化不变量：coverage、字段/类型闭包、subject lineage、输入 dataflow、effect/postcondition 和 fallback；开放语义仍由 agent 判断。

## 新 library split 的建议协议

新的 93/97 template split 应取代旧 T2，作为正式 cross-template 主实验：413 train tasks 建库，399 test tasks 评测。真正的 builder 输入不是 task ID 本身，而是 train tasks 中成功且通过 gold gate 的 standalone workflows，因此必须同时报告：

- planned train tasks/templates；
- successfully solved tasks；
- gold-admitted workflows；
- 每个站点/feature 的最终 primitive coverage。

同模板 T1 仍可保留为独立诊断，但必须从 train templates 内另行留出实例并重建库，不能使用已经看过这些实例的 413-task library。

`library_split/` 当前尚未同步到本工作树，因此本分支暂不包含那三个 split JSON 和生成脚本；它们到位后应作为独立 commit 加入，不应从统计表反向伪造 task IDs。

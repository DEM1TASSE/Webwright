# Map primitive regression：发现、根因与版本演进

日期：2026-08-17  
实验：WebArena Map，T2 cross-template retrieve tasks  
模型：gpt-5.4  
评测集：10 个 library-unseen templates，共 19 个 tasks

## 1. 一句话结论

最初的 regression 不是因为“代码复用没有价值”，而是因为 primitive 同时承担了三件不该混在一起的事：站点 acquisition、候选集定义和任务语义选择。前者适合复用，后两者容易锚定 agent 的策略。

Map 上的演进因此经历了三步：

1. 修正 primitive contract，使其正确封装站点知识；
2. 补 candidate-set acquisition，但不让 primitive 决定查询词、类别和最终候选；
3. 对 chained open-world task 延迟曝光，只复用不参与实体选择的 objective operator。

当前最可信的完整运行是 v7：与 clean scratch 同为 **14/19**，但产生 **1 win / 1 loss**；13 个双方都正确的任务上，平均 steps 从 **16.08 降到 8.46**。之后的 route-only policy 定向修复了唯一已知 loss，但目前只有 affected-case 增量验证，还不是新的完整 19-task 结果。

## 2. 固定基线与结果口径

Clean scratch 使用同一批 19 个任务：

| 方法 | 正确率 | 全部任务平均 steps | 正确任务平均 steps |
|---|---:|---:|---:|
| Clean scratch | 14/19（73.7%） | 17.47 | 16.07 |

本文区分三类证据：

- **Full run**：19 个任务全部重新运行，可以报告整体正确率；
- **Pilot**：只运行少量预选任务，用于开发和定位，不估计总体正确率；
- **Incremental affected-case regression**：冻结某次 full run，只替换受新改动直接影响的任务，用于证明已知 regression 是否修复，不能冒充 fresh full run。

## 3. 最初如何发现 regression

### 3.1 v4：初始生成库，完整运行明显低于 scratch

| 方法 | 正确率 | 平均 steps |
|---|---:|---:|
| Clean scratch | 14/19（73.7%） | 17.47 |
| Primitive v4 | 7/19（36.8%） | 9.79 |

v4 速度看起来更快，但正确率下降 36.8 个百分点。这不是有效的效率收益，而是 agent 更快地收敛到错误答案。

v4 暴露出的第一个 contract 问题是 routing：

```python
get_route(waypoints, profile="driving", base_url="...:5000")
```

Map deployment 中交通方式不是一个可以随意组合的 `profile + endpoint`。walking、driving、biking 分别绑定不同端口，而底层路径 profile 仍可能写成 `driving`。把这些低层参数独立暴露给 consumer，会产生表面合法、实际错误的组合。

第二个问题是 geocoding 只有 ranked、limited、query-scoped 结果，却容易被 consumer 当成完整候选集。对 `all / nearest / vicinity / NOT_FOUND` 任务，单次搜索为空或缺少某个候选，不能证明网站中不存在答案。

### 3.2 最小 verifier pilot：证实问题始于 induction contract

在 10 个冻结 retrieval proposals 上重放 contract verifier：

- Shopping task 225 和 Admin task 215 可通过；
- Shopping task 387 因 `product_id` 不可达被拒绝；
- 7 个 Map proposals 全部被拒绝，因为 v4 routing 暴露了相互耦合的 endpoint/profile，却没有 machine-readable configuration guarantee。

这个 pilot 得到的关键结论是：retrieval-time verifier 可以拒绝危险复用，但不能替 induction 修复错误 contract。若 library 没写清楚 scope、completeness 和配置耦合，retriever 只能全部 skip。

## 4. 根因分析

### 4.1 Contract 没有封装真正的站点知识

Primitive 应该封装：

- endpoint、port、selector、CSRF、pagination；
- 站点返回格式、单位和解析语义；
- 交通方式与 deployment 配置的耦合；
- typed objective output。

不应把这些知识留给每个 workflow 重新猜。例如早期 routing UI 返回 `0:04`，它在站点上表示 `H:MM`，consumer 却按 `M:SS` 解释成 4 秒。返回无类型 DOM，再让 task layer 自己理解单位，是错误的 contract 边界。

### 4.2 Partial acquisition 被误当成完整 candidate set

单个 query 返回正确结果，不等于它覆盖了任务所需的全部候选。尤其是：

- “所有 5km 内的机场”；
- “最近的药店”；
- “机场附近的 Hilton，再找每家最近的 supermarket”；
- 空结果后输出 NOT_FOUND。

这些任务需要区分：

```text
执行一次站点搜索（primitive 可拥有）
选择哪些 query 才足够（workflow 拥有）
判断候选是否属于目标类别（workflow 拥有）
判断候选集是否足以支持 all/nearest/absence（contract + workflow）
```

### 4.3 Exposure 本身会改变策略

即使 agent 没有真正调用 primitive，只要在规划前看到函数、endpoint、示例 query 和返回字段，也可能改变搜索策略。因此：

```text
retrieved ≠ incorporated ≠ executed ≠ accepted ≠ causally helpful
```

Map task 33 是代表性案例。完整注入 geocoding + routing 后，agent 被搜索路径锚定到 Hampton Inn 或 Hilton Garden Inn；API 调用可以完全成功，但 upstream hotel selection 已经错了。

### 4.4 全 skip 同样可能丢失必要站点知识

task 33 在一次 scratch-like 路径中选对了 DoubleTree 和 ALDI，却调用公网 OSRM，得到 `1.5km`。本地 Map deployment 返回 evaluator 需要的 `1.4km`。

因此正确边界不是“全部 adapt”或“全部 skip”：

- 酒店和 supermarket 的 discovery/selection 保持 scratch；
- 已选坐标之间的 site-coupled routing 仍应复用。

### 4.5 Consumer 方差会掩盖小幅方法差异

同一 library、同一 19-task set 的不同 fresh run 曾得到 14/19 和 11/19。变化主要来自 agent 自己生成的 query、候选选择和 fallback，而不是 primitive 代码发生变化。

所以单次相差 1–2 个任务不足以证明方法稳定提升；必须保留 paired case、重复运行或 majority/mean 统计。

## 5. Map 各版本改了什么

### 5.1 v4：初始 primitive library

主要设计：

- `search_places`：单 query Nominatim search；
- `search_local_geocoder_results`：local geocoder；
- `get_route`：caller 直接提供 `profile` 和 `base_url`；
- 直接注入完整函数作为 synthesis material。

结果：**7/19**。主要问题是低层配置暴露、缺少 machine-readable guarantees，以及 partial search 对 candidate-set task 的错误锚定。

### 5.2 v5：semantic routing contract + guarantees

主要改动：

1. `get_route(waypoints, transportation_method)` 只暴露 `driving | walking | biking`；
2. primitive 内部隐藏端口与底层 profile 的完整映射；
3. 增加 `collection_scope / completeness / supports_absence_proof / configuration`；
4. search 明确为 partial，不能证明 absence；
5. 增加 acceptance checks、workflow attribution、batch snapshots 和 consolidation overlap gate。

完整结果：

| 方法 | 正确率 | 平均 steps | 正确任务平均 steps |
|---|---:|---:|---:|
| v4 | 7/19 | 9.79 | 9.57 |
| v5 | 12/19 | 11.68 | 10.58 |

相对 v4，v5 有 5 个 win、0 个 loss，证明 contract 修复确实有效：

- task 364：walking distance 从错误的 `1.6km` 修成 `1.7km`；
- task 80/81：walking + driving 的组合任务恢复正确；
- task 218：正确处理 5 分钟 walking threshold；
- task 220：去掉额外酒店。

但相对 scratch 仍有两个 loss：task 8 和 task 33，二者都是 open-world candidate-set 问题。这说明“primitive 单次 acquisition 正确”仍不等于“candidate set 足够”。

### 5.3 v6：扩大 typed coverage 的困难案例 pilot

v6 继续尝试提高 acquisition coverage：

- `search_places` 增加 address、extratags、namedetails 和 bounded scope 信息；
- 同时保留 semantic `get_route` 与 narrower `get_driving_route`；
- 增加 local geocoder variants；
- router 通过 contract verifier 选择 use/adapt/skip。

只运行了 6 个困难任务，因此它是 pilot，不是总体结果：

| task | 结果 | 观察 |
|---:|---:|---|
| 8 | ✓ | richer geocoding + driving route 能支持机场任务 |
| 80 | ✓ | semantic multi-mode routing 有效 |
| 364 | ✓ | walking deployment 正确 |
| 33 | ✗ | Hilton/supermarket 的 chained candidate selection 仍被锚定 |
| 236 | ✗ | pharmacy query/selection 仍不稳定 |
| 237 | ✗ | gas-station discovery 和 nearest selection 不完整 |

v6 的教训是：扩大字段 coverage 能修复信息缺失，却无法解决“哪些 query 和候选才对”的任务语义；过多重叠 primitives 还增加 retrieval noise。

### 5.4 v7：multi-query acquisition + consolidation + typed bounds

v7 将库收敛为四个边界更清楚的 primitives：

- `search_places`：单 query，明确 partial；
- `search_local_geocoder_places`：站点 local geocoder；
- `search_places_collection`：执行 caller 提供的多组 query、合并并按稳定 OSM identity 去重；
- `get_route`：semantic transport mode，隐藏 deployment coupling。

Induction/validation 同时加入：

- multi-query loop + stable-ID dedupe 必须提取，不能退化为单 query；
- query 词、类别过滤、nearest/ranking 仍归 workflow；
- bounds 使用 `{minlon,minlat,maxlon,maxlat}` typed object；
- primitive 内验证顺序并序列化 viewbox；
- UPDATE 只能 backward-compatible widening；
- COVERED 不能丢掉 source candidate 的 objective output fields；
- 不允许 raw DOM/page text、task-specific semantic filter 和 client-side haversine 进入 primitive。

完整结果：

| 方法 | 正确率 | 全部任务平均 steps | 正确任务平均 steps |
|---|---:|---:|---:|
| Clean scratch | 14/19 | 17.47 | 16.07 |
| v7 | 14/19 | 9.42 | 8.50 |

Paired 结果：

- win：task 236；
- loss：task 33；
- 13 个双方都正确的任务，steps 从 16.08 降到 8.46，下降 47.4%。

这说明 v7 已经恢复总体正确率并显著降低成功任务的 agent steps，但收益与 regression 抵消，核心边界仍未完全解决。

### 5.5 v7-router2：仅靠 use/adapt/skip prompt 不够

针对 task 236/237/33 做了三任务 development check：

- task 236：正确；
- task 237：错误；
- task 33：错误。

Router 能说出“open-ended candidate discovery 需要 multi-query acquisition”，但无法稳定判断 primitive exposure 是否会改变上游实体选择。自然语言 `use/adapt/skip` 只能作为 proposal，不能单独承担最终安全决策。

### 5.6 v7 typed-bounds targeted check：修复输入 shape，但不是完整答案

旧接口允许 consumer 传 opaque viewbox string，task 33 曾出现坐标顺序错误。改成 typed bounds 后，单任务 targeted E2E 得到：

```json
[{"hotel":"DoubleTree by Hilton Hotel Pittsburgh Airport","distance":"1.4km"}]
```

结果为 **task 33：正确，11 steps**。

这证明 typed contract 能修复 malformed request，但仍不能保证每次 consumer 都选到同一酒店。因此它是必要改进，不是 strategy anchoring 的充分解。

### 5.7 v8：chained-open-world risk gate 的完整重跑

v8 在 retrieval 前识别 chained/open-world risk：若一个未完全命名的上游实体决定后续搜索 anchor，则不提前曝光 candidate-acquisition primitives。

完整运行结果：**11/19，平均 12.05 steps**。

典型变化：

- task 33：skip 后选对 DoubleTree，但用了公网 OSRM，输出 `1.5km`，仍错；
- task 236：仍 adapt，但采样时选择 Rite Aid，原来的 win 消失；
- task 237：skip 后本次转对；
- task 367：skip 后选择/路由异常，转错。

v8 的意义不是“新 policy 更差”，而是揭示两个问题：

1. 全 skip 会同时丢掉危险的 candidate anchoring 和有价值的 site deployment knowledge；
2. consumer sampling variance 足以让单次 full run 波动 3 个以上任务。

因此不能用 v8 的 11/19 否定 primitive，也不能用某次单点成功声称稳定提升。

### 5.8 v10：late-bound objective operator

最终规则从“危险任务全部 skip”改为更细的边界：

```text
候选发现与语义选择：scratch/workflow
消费已选 concrete IDs/coordinates 的客观算子：允许 late-bound primitive
```

对于 task 33：

1. planning 阶段不曝光 geocoding/candidate collection；
2. agent 自己选择酒店和 supermarket；
3. 只有当具体坐标已确定后，才注入 `map/routing/get_route`；
4. verifier 排除输出 `results/places/candidates` 的 acquisition primitive；
5. 对 negative risk classification 复核一次，并用 typed-contract fallback 恢复安全 objective operator。

Targeted E2E：task 33 恢复为正确的 DoubleTree / `1.4km`，18 steps。连续三次 retrieval probe 都只选择 routing。

若冻结 v7 的其他 18 个结果，只替换 task 33，则增量结果为：

| 方法 | 正确率 | 平均 steps | paired |
|---|---:|---:|---:|
| Clean scratch | 14/19 | 17.47 | — |
| v10 incremental | 15/19 | 9.79 | 1 win / 0 loss |

这里的 15/19 是 affected-case regression result，不是 fresh v10 full run。它能证明已知 loss 被修复，不能证明真实总体均值已经稳定达到 78.9%。

## 6. task 33：同一个 regression 如何逐步被定位

| 版本 | 给 agent 的材料 | 结果 | 原因 |
|---|---|---|---|
| Scratch | 无 library | DoubleTree / 1.4km，历史基线正确 | 自主发现候选并使用正确 deployment |
| v5/v6 | geocoding + routing | 错误 Hilton/Hampton 候选 | candidate exposure 锚定上游选择 |
| v7 full | collection + routing | Hampton Inn / 1.5km，错误 | 更强 acquisition 仍没有解决语义选择 |
| v7 typed bounds | collection + routing，typed bounds | DoubleTree / 1.4km，正确 | 修复 malformed bounds，但单次 targeted |
| v8 | 全 skip | DoubleTree / 1.5km，错误 | 候选选对，但丢失本地 OSRM deployment |
| v10 | 只 late-bind routing | DoubleTree / 1.4km，正确 | discovery 留给 scratch，站点 routing 继续复用 |

这个案例最终给出的边界是：

> Primitive 可以拥有“如何从站点取得客观事实”，但不能因为自己能搜索，就获得“当前任务应该搜索什么、选谁作为下一个 anchor”的权力。

## 7. 最终设计原则

### 7.1 Induction

- primitive 封装站点机制和 typed parsing；
- workflow 保留 query choice、semantic filtering、ranking、aggregation 和 final formatting；
- candidate collection 可以执行 caller-supplied query family 和 stable-ID dedupe，但不能声称 query family 完备；
- absence proof 只有在 acquisition 明确 complete 时才允许；
- 不返回 Locator、raw DOM、page text 或 opaque site parameters；
- site-coupled configuration 必须隐藏在 semantic input 后面。

### 7.2 Retrieval

- exact workflow、primitive、scratch 是不同通道；
- `use/adapt/skip` 由 LLM 提议，deterministic verifier 约束；
- chained open-world task 不在 planning 前曝光 candidate-acquisition code；
- 可以 late-bind 不参与候选选择的 objective operator；
- primitive empty/failure 触发 scratch fallback，不能直接解释成 NOT_FOUND。

### 7.3 Evaluation

- scratch 与 primitive arm 必须严格目录隔离；
- 报告 retrieved、incorporated、execution-reached、acceptance-passed 和 fallback；
- full run、pilot 和 incremental result 分开报告；
- 单次 1–2 task 差异不作为稳定结论，后续需要重复运行和 cluster-aware 统计。

## 8. 版本结果总表

| 版本 | 类型 | 任务数 | 正确 | 主要结论 |
|---|---|---:|---:|---|
| Scratch | full baseline | 19 | 14 | 固定 clean control |
| v4 | full | 19 | 7 | 初始 contract 与 exposure 严重 regression |
| v5 | full | 19 | 12 | semantic route contract 显著修复，但仍低于 scratch |
| v6 | hard-case pilot | 6 | 3 | richer typed coverage 有效，candidate semantics 仍失败 |
| v7 | full | 19 | 14 | 与 scratch 打平；1 win / 1 loss，steps 明显下降 |
| v7-router2 | targeted | 3 | 1 | prompt-only routing 不足 |
| v7 typed bounds | targeted | 1 | 1 | 修复 task 33 input-shape failure |
| v8 | fresh full | 19 | 11 | 暴露全 skip 代价与 consumer 方差 |
| v10 route-only | targeted | 1 | 1 | 修复 task 33 已知 loss |
| v10 incremental | affected-case | 19 | 15 | 仅证明已知 regression 修复，不是 fresh full run |

## 9. 相关产物

- 原因分类总文档：`docs/skill_factory/primitive_regression_analysis_2026-08-17.md`
- verifier pilot：`evals/webarena/primitive_verifier_minipilot/README.md`
- v4 library：`evals/webarena/reuse_split_v1_primitive_library_v4/map/final_candidate/`
- v5 library/result：`evals/webarena/reuse_split_v1_primitive_library_v5/`、`evals/webarena/reuse_split_v1_eval_results_v5/`
- v6 pilot：`evals/webarena/reuse_split_v1_eval_results_v6_pilot/`
- v7 library/full result：`evals/webarena/reuse_split_v1_primitive_library_v7/`、`evals/webarena/reuse_split_v1_eval_results_v7_final/`
- v7 router2：`evals/webarena/reuse_split_v1_eval_results_v7_router2/`
- v7 typed bounds：`evals/webarena/reuse_split_v1_eval_results_v7_typed_bounds/`
- v8 full：`evals/webarena/reuse_split_v1_eval_results_v8_final/`
- v10 late-bound task 33：`evals/webarena/reuse_split_v1_eval_results_v10_late_bound/`
- v10 incremental summary：`evals/webarena/reuse_split_v1_eval_results_v10_incremental/README.zh-CN.md`
- induction：`src/webwright/skill_factory/audited_primitive_build.py`
- retrieval/router/verifier：`evals/webarena/cross_task_eval.py`


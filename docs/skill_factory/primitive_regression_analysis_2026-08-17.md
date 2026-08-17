# Cross-template primitive regression：原因、修复尝试与当前结论

日期：2026-08-17  
范围：WebArena retrieve tasks，重点分析 Map T2（library-unseen templates）

## 1. 结论先行

Primitive regression 不能简单解释为“primitive 没用”。目前观察到三种性质不同的问题：

1. **Contract 错误**：primitive 没封装真正的站点知识，或输入/输出 schema 不足以防止误用。
2. **Consumer anchoring**：primitive 本身返回正确事实，但代码曝光改变了 agent 的 query、候选集或语义选择。
3. **实验噪声**：同一配置下 agent 的候选发现、fallback 和工具选择有较大方差；环境污染、timeout 和 evaluator 版本还会制造伪差异。

当前最有效的设计原则是：

> Candidate discovery 和语义选择由 workflow/scratch 负责；primitive 只拥有站点绑定 acquisition 与 typed parsing。若任务存在“先选择未完全命名的实体，再以它为锚点执行第二轮搜索”的链式开放世界分支，只能 late-bind 不参与实体选择的 objective operator，例如消费已选坐标的 routing primitive。

Map 的干净 scratch 为 **14/19**。v7 完整运行也是 **14/19**：task 236 是 win，但 task 33 是 loss，净增益为 0。对 task 33 使用 route-only late binding 后，该 regression 被定向修复；以冻结 v7 为基底的 affected-case 增量回归结果为 **15/19**。这不是一次新的 19-task 全量采样，不能替代后续 full rerun。

## 2. 主要 regression 原因

### 2.1 Contract 边界画错：把站点语义留给 task layer

早期 `route_between` 返回整个 DOM `Locator`，并要求 task layer 自己解析时间。Map UI 的 `0:04` 表示 `H:MM`，但 consumer 按 `M:SS` 解析成 4 秒。Primitive 成功导航并读到了正确页面，最终答案仍错了 60 倍。

根因不是 selector 失败，而是 primitive contract 没有封装最关键的站点知识：

- 错误边界：`Locator -> task 自己理解单位`
- 正确边界：`{"duration_seconds": int, "distance_meters": float}`

因此，“filter、aggregation、final formatting 留给 workflow”是对的；“站点返回格式、单位和解析约定也留给 workflow”是错的。

### 2.2 Candidate-set contract 不完整

很多任务要求 `all / nearest / vicinity / within N minutes`。单次 search primitive 即使执行正确，也只返回某个 query 的结果，不能证明：

- query family 足够完整；
- 没有遗漏候选；
- 当前结果支持 global nearest；
- 空结果可以推出 NOT_FOUND。

如果 router 把“相关 search”误当成“核心 candidate acquisition 已覆盖”，agent 会停止自己的 discovery，产生 false negative 或错误 nearest。

后续增加了 `collection_scope`、`completeness`、`supports_absence_proof`，并生成 `search_places_collection`，负责执行 caller 给出的多组 query、合并结果、按稳定 OSM ID 去重。但它仍然只保证“执行了全部 caller-supplied searches”，不保证 caller 选择了完备的 query family。

### 2.3 Semantic anchoring：正确代码改变了错误的决策

Primitive injection 本身就是 intervention。即使 agent 最终没有真正调用函数，看到函数、endpoint、示例 query 和字段也会改变其策略。

Map task 33 是最清楚的例子：

- 任务先要求选择 Pittsburgh Airport 附近的 Hilton；
- 再以该酒店为锚点寻找 supermarket；
- 最后比较 walking route。

完整注入 geocoding + routing 后，agent 有时选择 Hampton Inn，有时选择 Hilton Garden Inn；primitive 的 acquisition 没有报错，但 upstream hotel selection 被曝光的搜索路径锚定。相同机制在某些任务是 win，在另一些任务是 loss。

这说明“函数被执行成功”不等于“primitive 对任务有帮助”。帮助性取决于它是否介入了本应由当前 goal 决定的语义分支。

### 2.4 Site deployment coupling 丢失

完全 skip primitive 也不总是安全。task 33 的一次 scratch-like run 选对了 DoubleTree 和 ALDI，却调用公网 `router.project-osrm.org`，得到 `1.5km`；站点对应的本地 OSRM deployment 返回 `1.4km`，与 evaluator gold 一致。

这类 endpoint、port、profile 和运输模式映射属于站点知识，应该由 primitive 封装。于是 task 33 不能简单“全 adapt”或“全 skip”：

- geocoding/candidate discovery 不能提前曝光；
- routing deployment 应该复用；
- 正确策略是 route-only late binding。

### 2.5 输入 shape 与隐式配置错误

旧 Map primitive 曾让 consumer 直接传 opaque `viewbox` 字符串。task 33 出现过 malformed ordering，导致有界搜索结果错误。后续改为 typed bounds：

```json
{
  "minlon": -80.4,
  "minlat": 40.4,
  "maxlon": -80.1,
  "maxlat": 40.6
}
```

Primitive 内部验证 `min < max` 并序列化为站点参数。原则是：公开 contract 使用有语义、可验证的类型；opaque site parameter 留在实现内部。

### 2.6 空结果与 fallback 被误解释

Consumer 常见错误是：

1. primitive 返回空或 partial；
2. agent 直接输出 NOT_FOUND；
3. 没有恢复原 scratch acquisition。

正确语义应该是：primitive failure/empty 只表示该局部 acquisition 没通过 acceptance check，不表示网站事实不存在。只有 contract 明确支持该 scope 的 absence proof，才允许把空结果变成 NOT_FOUND。

### 2.7 Provenance marker 高估真实使用

有的 final script 保留 `# primitive-source`，随后却绕过 primitive 调用另一条 API 路径。因此以下信号都不足以证明行为归因：

- 代码被注入；
- marker 出现在脚本；
- primitive body 被复制进 final script。

真正需要的是 execution trace：`entered -> completed -> acceptance_passed/failed -> fallback_used`。当前实验中 trace 覆盖仍不完整，所以结果报告必须区分“retrieved / incorporated / execution-reached / accepted”。

### 2.8 Consumer 采样方差

Map 同一个 19-task set 上出现过：

- clean scratch：14/19；
- v7 primitive：14/19；
- 后续一次 fresh v8 full rerun：11/19。

v8 的退化不是 library 突然变坏：task 236 曾由 wrong -> correct，下一次却选择 Rite Aid 而失败；task 237 在 skip 后又随机转对；task 367 在 skip 后选择了错误 CVS。主要变化来自 agent 自己生成的 query、候选集和 fallback。

因此单次 full run 不能区分小幅方法差异。正式结论至少需要多 run、cluster-aware 统计，或预注册 majority/mean 指标。

### 2.9 实验污染、timeout 与 evaluator 版本

此前发现 scratch 和 primitive 共用目录时，scratch agent 能读到相邻 primitive artifact，导致所谓 scratch 不是干净 control。另一次 PATH 问题让 22/24 个任务退化为 curl-only。高并发还会增加超时，而 timeout 曾被算成 benchmark failure。

已采取的控制包括：

- `--strict-arm-isolation`；
- scratch/primitive 独立 runs root；
- 记录 evaluator commit；
- 检查 null expected-data fix；
- agent 写出完整 `agent_response.json` 后立即停止，避免完成后继续反思导致 timeout；
- 区分 `agent_timeout_or_incomplete` 和 infrastructure error。

## 3. 尝试过的方案及效果

### 3.1 直接完整注入 primitive

做法：router 选择 geocoding、routing 等函数，将完整代码作为 synthesis material 注入，agent vendor 到 standalone `final_script.py`。

优点：

- 能传递 endpoint、CSRF、pagination、parser、单位等站点知识；
- 不产生 runtime dependency；
- 历史 workflow 不受 catalog 更新影响。

问题：

- pre-planning exposure 会改变整体策略；
- 大函数增加上下文和步骤；
- generic search 容易锚定错误 candidate set。

结论：保留 vendoring，但不能默认“相关即注入”。

### 3.2 `use / adapt / skip` router prompt

做法：

- `use`：primitive 覆盖完整站点 acquisition；
- `adapt`：覆盖一个可闭合的局部 acquisition；
- `skip`：只相关但不能替换具体工作，或会造成不完整策略。

效果：比无条件注入更好，但纯自然语言规则不稳定。同一 task 33 有时 route-only，有时 skip；router 的 reason 甚至会说“routing 是安全的”，结构化 ID 却返回空数组。

结论：LLM router 只能提议，最终集合必须由结构化 verifier 约束。

### 3.3 Scratch-first plan + local patch

做法：先在看不到 library 的条件下生成 scratch plan，再允许 primitive 替换一个命名 step，其余步骤冻结。

目标：避免 library 重写整体策略。

观察：语义上最干净，但增加一次 planning 调用和 prompt 长度；之前小样本没有显示稳定收益，step 成本较高。它仍是完整版方向，但不是当前最小 direct MVP 的默认路径。

### 3.4 Contract verifier

验证三项：

1. `input_reachability`：输入来自 task、scratch 或前序输出；
2. `guarantee_sufficiency`：contract 足以支持所声称的局部替换；
3. `closed_acquisition`：至少一个 acquisition 被完全替换，而不是只增加一次 probe。

效果：能挡住缺内部 ID、缺配置值、单页结果冒充完整集合等问题。但它验证的是局部 contract，不自动保证 exposure 不会影响上游语义选择，因此还需要 exposure-risk gate。

### 3.5 Typed bounds + multi-query + stable-ID dedupe

做法：

- bounds 从 opaque string 改为数值对象；
- primitive 内部序列化 viewbox；
- 多 query 一次执行；
- 以 `(osm_type, osm_id)` 去重；
- query 选择、semantic filter、ranking 留给 workflow。

效果：修复了 malformed viewbox；task 33 的 typed-bounds targeted run 得到正确的 DoubleTree / 1.4km。它提高 acquisition 质量，但不能单独解决“该选哪个酒店”的语义问题。

### 3.6 Chained-open-world skip gate

初版规则：若未完全命名的上游实体决定后续 search/nearest，则全部 skip。

效果：消除了错误酒店 anchoring，却让 task 33 scratch 使用公网 OSRM 得到 1.5km；task 367 也因完全 skip 失去站点 routing 知识而失败。

结论：全 skip 太粗。

### 3.7 Late-bound objective operator

当前规则：

- 开放候选发现和语义选择保留给 scratch；
- 只允许消费已选 concrete ID/coordinates、返回 objective facts、且不输出 candidate collection 的函数；
- task 必须明确需要该 output concept，例如任务包含 distance/time/OSRM，才允许 distance/duration operator；
- typed schema 出现 `results/places/candidates` 时排除。

task 33 因此只拿到 `map/routing/get_route`。Targeted E2E 从错误结果恢复为：

```json
[{"hotel": "DoubleTree by Hilton Hotel Pittsburgh Airport", "distance": "1.4km"}]
```

### 3.8 风险分类复核 + 静态 fallback

仅靠一次 LLM risk classification 仍有 false negative。当前实现：

- negative classification 复核一次；
- 两次意见冲突时采用更安全的 chained verdict；
- safe-ID LLM 只作 advisory；
- typed task-contract verifier 可以从 catalog 恢复被第一层漏掉的 objective operator。

task 33 连续 3 次 retrieval probe 均稳定为 route-only。代价是多一次 metadata-only routing 调用；是否值得需要后续报告 routing token/latency。

### 3.9 Primitive induction guardrails

Inducer 当前增加了：

- 不允许 primitive 内做 task-specific semantic filter/ranking；
- 不允许用 client-side haversine 冒充网站 route distance；
- looped multi-search + dedupe 应提取成独立能力；
- UPDATE 必须保持既有 input shape，breaking change 用 ADD；
- COVERED 必须真正覆盖 required output fields；
- 拒绝未类型化 DOM 返回值和 opaque viewbox；
- evidence 用于 provenance 检查，但不要求逐字复制硬编码 workflow，允许参数化。

这些规则提高生成库的 contract 质量，但无法消除 consumer 的语义方差。

## 4. 当前数字应如何解释

### 4.1 可直接陈述

- Map clean scratch：14/19，73.7%。
- Map v7 full primitive：14/19，73.7%。
- v7 paired：task 236 为 win，task 33 为 loss，净 0。
- task 33 route-only targeted E2E 修复成功。
- route-only retrieval 连续 3 次 probe 稳定。

### 4.2 只能标成增量回归结果

冻结 v7 的其他结果，只替换被新 gate 影响并重跑的 task 33，可得到 15/19，78.9%，paired 1 win / 0 loss。该结果证明已知 regression 被修复，但不是一次 fresh 19-task sampling。

### 4.3 暂时不能声称

- 不能说 v10 已在完整 fresh run 上稳定达到 15/19；
- 不能用一次 11/19 或 15/19 推断真实均值；
- execution trace 不完整时，不能把所有差异严格归因于 primitive body 被执行。

## 5. 下一步实验建议

1. 冻结 library、router prompt、模型配置和 evaluator commit。
2. 先在 GitLab、Shopping、Shopping Admin 的 T2 上运行，检查 Map 现象是否跨站成立。
3. 每个 arm 至少重复 3 次，报告 task-level majority、均值和方差。
4. 单独报告 retrieval decision、injected tokens、incorporation、execution-reached、fallback。
5. 将 task 分为 fully named lookup、single-stage open-world、chained open-world，再报告分组收益。
6. 若 late-bound operator 跨站有效，再把 `composition_role` 正式加入 induction schema；在此之前保持它是 verifier 推导属性，而不是新的运行时层级。

## 6. 相关产物

- Map 增量结果：`evals/webarena/reuse_split_v1_eval_results_v10_incremental/`
- Map v7 full：`evals/webarena/reuse_split_v1_eval_results_v7_final/`
- Map v8 noisy full：`evals/webarena/reuse_split_v1_eval_results_v8_final/`
- Map v10 task 33：`evals/webarena/reuse_split_v1_eval_results_v10_late_bound/`
- Router/contract verifier：`evals/webarena/cross_task_eval.py`
- Primitive induction：`src/webwright/skill_factory/audited_primitive_build.py`
- Primitive retrieval/rendering：`src/webwright/skill_factory/audited_primitive_retrieve.py`

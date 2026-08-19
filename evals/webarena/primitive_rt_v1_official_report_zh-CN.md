# WebArena Cross-Template Primitive V9 实验报告

日期：2026-08-18
模型：gpt-5.4
任务范围：WebArena 单站点 Retrieve + Navigate
比较：Scratch vs. Primitive-only（不注入 workflow）

## 1. 结论

本轮完成了从 TRAIN workflow、官方 evaluator admission、V9 primitive 自动建库，到 unseen-template held-out 配对测试的完整闭环。所有 primitive 均由通过 evaluator 的 workflow 自动生成，没有人工编写 primitive。

V9 primitive 在当前单次全量运行中**没有取得稳定的总体正确率提升**：

| 指标 | Scratch | Primitive | 变化 |
|---|---:|---:|---:|
| Micro accuracy | 65/156 = 41.67% | 62/156 = 39.74% | -1.92 pp |
| Macro template accuracy | 36.4% | 42.2% | +5.8 pp |
| 平均 agent steps | 18.404 | 18.019 | -0.385（-2.1%） |
| Timeout / incomplete | 10 | 16 | +6 |

配对结果为 20 wins、23 losses、42 both-correct、71 both-wrong。57 个 held-out templates 中，14 个提高、12 个回退、31 个不变。按模板聚类 bootstrap 的宏平均差值 95% CI 为 `[-5.1 pp, +16.9 pp]`；20 对 23 的条件配对检验 `p=0.761`。因此不能把本轮结果解释为稳定的总体收益。

但实验揭示了一个明确的设计信号：**当 router 能高置信判断 primitive 完整覆盖具体站点操作（`use`）时，收益集中且没有观察到回退；宽松的局部适配（`adapt`）则不稳定。**

| Router decision | n | Win / Loss | 正确率净变化 | 平均 steps 变化 |
|---|---:|---:|---:|---:|
| use | 11 | 4 / 0 | +4 tasks | -5.909 |
| adapt | 29 | 4 / 7 | -3 tasks | -0.655 |
| skip | 116 | 12 / 16 | -4 tasks | +0.207 |

`skip` 不暴露 primitive 代码，因此其 12/16 差异主要反映两个独立 agent sample 的运行方差，而不是 primitive 的行为效果。当前 run 还存在一个已修复的小控制缺陷：`skip` prompt 比 scratch 多一个开头换行；后续运行已经做到真正的空提示 no-op。

## 2. 数据划分与执行完整性

划分文件：[primitive_rt_template_disjoint_v1.json](primitive_rt_template_disjoint_v1.json)

- TRAIN：56 个 templates，每个 3 个实例，共 168 个 source tasks。
- TEST：57 个从未进入 library 的 templates，共 156 个 tasks；同一 held-out template 的所有实例都进入测试。
- TRAIN 与 TEST template 严格不相交。
- 五个站点：GitLab、Map、Reddit、Shopping、Shopping Admin。
- 官方 WebArena task intent、start URL 和 evaluator 用于执行与评分；Verified 数据只用于 template/type 元数据。
- Retrieve/Navigate 不执行有状态 mutate，因此本轮不 reset 环境。

完整性检查：预期 312 条测试记录（156×2 arms），实际找到 312；missing、identity error、status error、arm isolation error 均为 0。

## 3. TRAIN admission 与 V9 自动建库

168 个 TRAIN workflow 先运行，再由官方 evaluator 做 gold admission：

| 站点 | Gold-admitted workflows |
|---|---:|
| GitLab | 10 |
| Map | 16 |
| Reddit | 4 |
| Shopping | 10 |
| Shopping Admin | 15 |
| 合计 | 55 / 168 |

其中 53 个是 Retrieve，只有 2 个是 Navigate。这会限制 Navigate primitive 的覆盖面，也是 held-out Navigate 绝对成功率很低的重要背景。

V9 induction 对每个站点执行：workflow 提取候选 → attribution/contract verifier → batch update → consolidation/organization → package verifier。最终生成 37 个 primitive：

| 站点 | Primitive 数量 |
|---|---:|
| GitLab | 11 |
| Map | 3 |
| Reddit | 5 |
| Shopping | 7 |
| Shopping Admin | 11 |

Library：[primitive_rt_v1_library_v9_guarded](primitive_rt_v1_library_v9_guarded/)
Gold manifest：[primitive_rt_v1_official_gold_manifest](primitive_rt_v1_official_gold_manifest/)

V9 相比旧版的核心约束是：

1. primitive 封装站点机制、typed parsing 和直接由站点报告的字段；query choice、开放世界候选完整性、跨结果 ranking/aggregation 留在 workflow。
2. 没有 source workflow 支撑的 semantic operation 会被自动移除，并重新编号 provenance metadata。
3. `count_*` 只允许读取站点直接报告的数量，不允许把 `len/sum` 等 workflow 聚合伪装成站点 primitive。
4. 对 Magento 等实际 schema 做语义别名归一化，但不放宽能力边界。
5. retrieval 输出 `use/adapt/skip`；只有 `use/adapt` 才向 agent 注入完整 primitive，`skip` 保持 scratch fallback。

## 4. Held-out 结果

### 4.1 按站点

| 站点 | Scratch | Primitive | 配对 Win/Loss | Steps Scratch→Primitive |
|---|---:|---:|---:|---:|
| GitLab | 9/21 | 9/21 | 3 / 3 | 14.286→13.524 |
| Map | 19/46 | 22/46 | 7 / 4 | 18.978→19.348 |
| Reddit | 0/2 | 2/2 | 2 / 0 | 17.000→13.500 |
| Shopping | 13/40 | 14/40 | 6 / 5 | 21.900→21.975 |
| Shopping Admin | 24/47 | 15/47 | 2 / 11 | 16.766→15.553 |

Map、Reddit、Shopping 有正向任务净值，但 Shopping Admin 的 -9 抵消了这些收益。Admin 的 11 个 loss 中有 9 个属于 `skip`、没有 primitive 代码曝光，不能归因于 primitive；另外 2 个是真正的 `adapt` exposure，且都失败，这是需要保留的真实负面信号。

### 4.2 按任务类型

| 类型 | Scratch | Primitive | Win/Loss |
|---|---:|---:|---:|
| Retrieve（125） | 65/125 = 52.0% | 60/125 = 48.0% | 18 / 23 |
| Navigate（31） | 0/31 | 2/31 = 6.45% | 2 / 0 |

Navigate 有两个新增成功，但两臂的绝对成功率都很低，且 TRAIN 只有两个 admitted Navigate source，当前不能据此声称 primitive 已解决 Navigate。

### 4.3 真正暴露 primitive 的子集

Router 在 156 个任务中选择 `skip=116`、`adapt=29`、`use=11`。因此只有 40 个任务看到 primitive 代码：

- exposed：8 wins / 7 losses，正确任务 17→18，平均 steps `-2.1`；both-correct 时 `-3.2` steps。
- not exposed：12 wins / 16 losses，平均 steps `+0.207`。
- 40 个 exposed 中有 37 个 final script 出现 primitive incorporation 证据。
- 本轮没有记录 execution-reached trace，因此只能说“代码被曝光/并入”，不能声称某个 primitive 的实际执行导致了结果。

这一区分很重要：总体 65→62 的主要下降不发生在实际 primitive exposure 子集，而发生在 no-op 的独立 sample 中。但 exposure 子集是 router 选择后的事后分组，不是随机实验，也不能单独当作无偏因果估计。

### 4.4 长尾信号

预定义统计脚本识别出的 long-tail 子集中有 44 个任务、34 个 templates：

- Scratch：13/44 = 29.55%
- Primitive：19/44 = 43.18%
- 8 wins / 2 losses，+13.64 pp micro，+14.7 pp macro-template
- 平均 steps `-0.636`；both-correct 时 `-4.636`

该结果符合 primitive 帮助“不常见但共享站点机制”任务的假设，但属于探索性 subgroup，必须通过重复运行或预注册的新 split 验证。

## 5. 本轮能支持与不能支持的结论

可以支持：

- 自动 pipeline 能从 55 个 gold-admitted workflows 建出五站、37 primitive 的可检索 package，并完成 unseen-template 消费闭环。
- 高置信 `use` 是当前最清楚的有效区域：11 个任务中 4 win / 0 loss，并显著减少步骤。
- `adapt` 边界仍然太松；“相关 primitive”不等于“对当前任务安全且足够”。
- primitive 的潜在价值更集中在长尾与具体站点机制，而不是对所有任务统一注入。

不能支持：

- 不能声称 primitive 在全部 unseen templates 上提高总体正确率；本轮 micro accuracy 反而下降 1.92 pp，置信区间跨 0。
- 不能把 `skip` 两臂的差异归因于 primitive。
- 不能从 marker/incorporation 推断 primitive 真正执行；缺少 execution trace。
- 不能从 Reddit 的 2/2 或 long-tail 单次结果推导稳定普遍收益。

## 6. 下一步

1. 将 `adapt` 收紧为“primitive 完整替代一个明确 acquisition/operator，且输入、输出与完整性 contract 均满足”；否则降级为 `skip`。最小消融是只允许 `use`。
2. 已修复 `skip` 的空提示，使 primitive arm 的 no-op 路径与 scratch prompt 字节级一致。
3. 加入 execution-reached instrumentation，区分 retrieved → exposed → incorporated → executed → accepted。
4. 固定同一 split 至少重复三次，并以 template cluster 为统计单位；先验证 `use-only` 与 long-tail 信号，再决定是否扩大规模。
5. 为 Navigate 增加通过 evaluator 的 source coverage；否则无法公平判断其跨模板复用能力。

## 7. 复现与产物

- Deployment：[primitive_rt_deployment_v1.json](primitive_rt_deployment_v1.json)
- TRAIN runs：[primitive_rt_v1_official_train_runs](primitive_rt_v1_official_train_runs/)
- TRAIN compact results：[primitive_rt_v1_official_train_results](primitive_rt_v1_official_train_results/)
- TEST runs：[primitive_rt_v1_official_test_runs](primitive_rt_v1_official_test_runs/)
- TEST compact results：[primitive_rt_v1_official_test_results](primitive_rt_v1_official_test_results/)
- 机器可读汇总：[primitive_rt_v1_official_test_summary.json](primitive_rt_v1_official_test_summary.json)

注：曾出现并发 runner 共用 compatibility split、被后启动站点覆盖的问题。该问题会让任务在启动前报“不属于 held-out split”，不会产出评分记录；现已改为每站独立 split，并只补跑缺失任务。最终 312 条记录均通过 identity/status/isolation 校验，废弃的进程错误未计入结果。

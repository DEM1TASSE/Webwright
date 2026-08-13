# WebArena reuse_split_v1 建库与评测报告

## 实验问题

比较复用半径不同的两类材料：同 template 的完整参数化 workflow，以及同网站、跨
template 的 v4 primitive。正式实验只包含 retrieve 任务。

## 冻结协议

- Split：`reuse_split_v1.json`；TRAIN/T1/T2 按 task 与 template 双重隔离。
- Workflow：commit `590beeab9b539cf938466e56128c4e5695a469ef` 的早期参数扩展
  pipeline；使用数据集官方 `intent_template` 分组，不接入 primitive。
- Primitive：commit `14b8adb` 的严格 v4 pipeline；primitive-direct，不使用
  scratch-first。
- Evaluator：commit `6473f72db5dcefc97b5725b59e734504edc28a21`。
- 模型：冻结的 `gpt-5.4` gateway 配置；单任务 timeout 900 秒。

## TRAIN 与建库

原始 121 个 TRAIN scratch solve 全部结束：66 correct、53 incorrect、2 timeout。正式评测前的
语义检查发现 task 792 是购买操作，不属于 retrieve；其失败运行保留供审计，但从正式 TRAIN
资格中剔除。因此正式 TRAIN 为 120 个任务，gold-admitted 仍为 66 个；任何失败、timeout、
mutation 或接触过 library material 的运行均未进入库。

正式评测包含 T1 70 个实例 / 35 个 template，以及 T2 59 个实例 / 33 个全新 template；报告
同时给出实例准确率和 template-macro accuracy，避免把同 template 实例误当成独立簇。

Workflow 仅在同一官方 template 至少有 3 个 gold source 时构建。Primitive 按网站汇总所有
gold source，依次保存 extraction、batch update、pre-consolidation、consolidation/organize 和
final candidate snapshots。

## Retrieval-only audit

188 条预执行 routing 记录完整且无 error：T1 exact workflow 为 use 22、skip 48；T2
workflow-adapt 为 adapt 23、skip 36；T2 primitive-direct 为 use 2、adapt 40、skip 17。
这证明三条 routing 通道可执行且任务覆盖完整；它不等价于行为收益，最终结论以 browser eval
为准。

## T1：同 template 新实例

| arm | correct | accuracy | template-macro | mean steps | timeout |
|---|---:|---:|---:|---:|---:|
| scratch | 44/70 | 62.86% | 62.9% | 15.29 | 2 |
| exact workflow | 42/70 | 60.00% | 60.0% | 13.70 | 1 |

配对结果为 10 win、12 loss、32 both-correct、16 both-wrong，net win = -2。Workflow
平均少 1.59 步；但 22 个实际 `use` 的样本为 2 win / 5 loss，48 个 `skip` 样本为
8 win / 7 loss。因此这版最早期参数扩展 workflow 没有带来正式准确率收益，步数下降不能抵消
正确率损失。

## T2：同网站、跨 template

| arm | correct | accuracy | template-macro | mean steps | timeout |
|---|---:|---:|---:|---:|---:|
| scratch | 43/59 | 72.88% | 74.2% | 15.15 | 1 |
| workflow-adapt | 33/59 | 55.93% | 56.1% | 13.68 | 5 |
| primitive-v4-direct | 37/59 | 62.71% | 65.2% | 11.44 | 0 |

相对 scratch：workflow 为 5 win / 15 loss（net -10）；primitive 为 7 win / 13 loss
（net -6）。Primitive 比 workflow 多答对 4 个，但仍没有打赢 scratch。Primitive 平均少
3.71 步（约 24.5%）；在双方都正确的 30 对上平均少 1.73 步。不过 primitive 错误运行
反而更短（10.77 步），说明总步数下降的一部分来自更早地产生错误答案，不应解释成纯效率收益。

### Primitive 按网站

| site | scratch | primitive | paired net | primitive mean steps |
|---|---:|---:|---:|---:|
| gitlab | 7/9 | 7/9 | 0 | 10.44 |
| map | 14/19 | 7/19 | -7 | 9.79 |
| shopping | 10/15 | 11/15 | +1 | 11.80 |
| shopping_admin | 12/16 | 12/16 | 0 | 13.63 |

负收益完全由 Map 贡献；另外三个网站合计不降准确率。Primitive E2E router 实际给出
`adapt=37 / use=3 / skip=19`，40 个被选择的任务都完整注入了代码，最终脚本也都检测到对应
primitive 特征；但声明式 usage 和 execution trace 都是 0，因此只能证明 exposure/incorporation，
不能仅凭 marker 声称函数真的执行过。按实际 route 分组：`adapt` 为 3 win / 10 loss，`use`
为 1 win / 0 loss，`skip` 为 3 win / 3 loss。`skip` 可视为本轮较有用的噪声对照，而主要损失
集中在 `adapt`。

### Map 失败分析

7 个 paired loss 全都 `adapt` 了同一对 primitive：`search_places` 与 `get_route`。产物检查
暴露出两个可复现的设计问题：

1. **耦合配置被错误拆成自由参数。** Map 后端用端口区分交通模式（训练证据中 walking 为
   5002、driving 为 5001），但 `get_route(profile, base_url=...:5000)` 让 consumer 独立组合
   profile 与 endpoint。多个失败脚本传入 `profile="foot"` 或 `"walking"`，实际响应的 route
   step 仍标记为 `mode="driving"`。这不是 task logic，而是 primitive 应封装并验证的站点契约。
2. **非完整候选集被当成核心 acquisition。** `search_places` 已声明 `is_complete=false`，但 router
   仍在“列出所有附近对象 / 阈值内对象 / 正确返回 null”类任务上选择 `adapt`，并把完整候选发现
   留在 remaining gap。结果包括 scratch 正确返回 null、primitive 却输出列表，以及正确列表被
   多加入对象。只要任务要求 exact set 或 NOT_FOUND，非完整候选查询就不能证明包含或排除。

因此本轮更准确的结论不是“primitive 一概无用”，而是：**一个 contract 不完整、同时被 router
过度适配的 primitive 对，可以抵消其他网站的中性或小幅收益。** 下一版应把 `transport_mode`
作为语义枚举，由 primitive 内部绑定并验证 endpoint/profile；同时为 candidate acquisition 增加
`complete/exhaustive/scope` 元数据，并硬性规定：任务的核心候选集未被覆盖时不得 `adapt`。

## Routing 稳定性

预执行 audit 与 E2E 共比较 188 条：decision 一致 176/188（93.6%），具体选择一致 175/188
（93.1%）。12 个 decision 漂移中，T2 workflow 有 7 个、primitive 有 5 个。Audit 证明的是
router 可执行，不是冻结后的实际 exposure；正式报告使用 E2E 记录。后续若要降低这部分方差，
应把一次 metadata routing 结果缓存为正式 manifest，再由 E2E 消费，而不是重新采样。

## 结论与下一步

当前结果不支持发布 v4 library：T1 workflow 与 T2 primitive 都未超过 scratch。下一步不建议直接
扩大同协议样本，而应先做一个针对 Map 的小回归：修复交通模式 contract、加入候选集完整性硬门禁，
只重跑上述 7 个 paired loss 及对应的原本正确 Map 样本，确认不会以修复 loss 为代价破坏已有
正确项。通过后再冻结 v5，并决定是否进行多 seed 或更大规模评测。

## 限制与异常

- 有效统计单位是 template；实例数只用于降低模板内噪声。
- Workflow gold gate 会降低实际覆盖率；缺少三个 gold source 的 template 在 workflow arm
  明确路由为 skip，而不是借用别的 template 冒充 exact match。
- 建库和运行中的所有需人工关注项记录在 `review_required.md`。
- 旧 sampler 只按 evaluator 类型过滤，曾混入 1 个 TRAIN 和 8 个 T2 mutation/不可执行任务；
  已在正式 browser eval 前剔除并写入 split metadata。正式规模为 T1 70、T2 59。
- 五个 arm 共 317 条记录均通过 identity、terminal status 和 strict arm isolation 校验；唯一一次
  process infrastructure error（T2 scratch task 208）通过 resumable runner 单独补跑成功，其他
  58 条没有重采样。
- 正式 E2E 使用 16 并发、每站最多 4。起始观察没有显示 16 相比先前 8 并发更快，因此没有在实验
  中途升到 24，以免改变冻结运行条件。
- 每个 arm 只有一次 agent 采样；配对与 `skip` 分组能减少误读，但不能替代多 seed 置信区间。

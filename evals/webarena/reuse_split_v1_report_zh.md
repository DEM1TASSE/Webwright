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

Workflow 仅在同一官方 template 至少有 3 个 gold source 时构建。Primitive 按网站汇总所有
gold source，依次保存 extraction、batch update、pre-consolidation、consolidation/organize 和
final candidate snapshots。

## Retrieval-only audit

188 条预执行 routing 记录完整且无 error：T1 exact workflow 为 use 22、skip 48；T2
workflow-adapt 为 adapt 23、skip 36；T2 primitive-direct 为 use 2、adapt 40、skip 17。
这证明三条 routing 通道可执行且任务覆盖完整；它不等价于行为收益，最终结论以 browser eval
为准。

## T1：同 template 新实例

待评测完成后填入 scratch 与 workflow 的配对结果。

## T2：同网站、跨 template

待评测完成后填入 scratch、workflow-adapt 与 primitive-v4-direct 的配对结果。

## 限制与异常

- 有效统计单位是 template；实例数只用于降低模板内噪声。
- Workflow gold gate 会降低实际覆盖率；缺少三个 gold source 的 template 在 workflow arm
  明确路由为 skip，而不是借用别的 template 冒充 exact match。
- 建库和运行中的所有需人工关注项记录在 `review_required.md`。
- 旧 sampler 只按 evaluator 类型过滤，曾混入 1 个 TRAIN 和 8 个 T2 mutation/不可执行任务；
  已在正式 browser eval 前剔除并写入 split metadata。正式规模为 T1 70、T2 59。

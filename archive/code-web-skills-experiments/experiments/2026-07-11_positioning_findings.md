# 定位三问:standalone vs agent 有用、聚合的必要性、缺失的 ablation

**日期:** 2026-07-11 ｜ 来源:裸跑审计(3/10)+ evolve+verify 复跑实验后的三连问。
initial release 先记账,后面慢慢补。

## 问题 1:验证关和 eval 证据打架

铁的事实:WebArena 的 +15pp 是用 **7/10 裸跑失败的库**跑出来的。t213 的 skill 裸跑
第一步就崩(相对 URL),但它救活了 held-out 任务——agent 读的是它携带的知识(哪个
网格、token 过滤、rating 单选框),不是执行它。

⇒ strict 拒收在优化 standalone 正确性的同时,会销毁对 agent 有用的知识。当时如果有
strict 关,库里只剩 3 个 skill,eval 数字大概率变差。

**结论:两个价值是两个等级,不该用一个开关杀掉另一个。**

| 等级 | 含义 | 实证 |
|---|---|---|
| verified(重放全过) | 真程序,standalone/cron 可用 | flights:三方一致、32s 零模型 |
| reference(重放没过) | agent 可读的知识载体 | WebArena +15pp 就是这个等级撑的 |

**待做(v2 候选,优先级高):** 把 evolve 的硬拒收改成分级入库——没过重放的照样落库,
meta 标 `verified: false / grade: reference`;standalone 接口拒跑或大声警告 reference
级;skill_use 的 JSON 透出等级。当前(initial release)的行为是硬拒收 + run 保留在
台账外可重试(fork 693d816),够用但偏保守。

## 问题 2:为什么不直接给成功脚本(final_script / craft)

- **单脚本 = 特解**:值硬编码、单策略、可能恰好没踩过坑(t217 的 token 过滤只存在于
  踩过坑的那次 solve 里,检索到另一份就漏了)。聚合 = N 个特解归纳成通解:共同部分=
  骨架,差异=参数,各自策略=fallback。
- **craft 是"猜",聚合是"看"**:crafted_cli 拿单次 solve 预判什么会变(会双向猜错);
  refine 的参数是 N 个实例间实际观察到的差异(flights 的 5 个参数、commit-period 的
  两种日期形态)。craft 的产物可以当聚合的输入,两者是上下游。
- **聚合什么时候不值**(该进 README 诚实段):任务家族只出现一次、或实例间几乎不变。
  收益 ∝ 复现频率 × 实例间变化幅度。

## 问题 3:缺失的 ablation(reviewer 必问,先认账)

eval 只比过 WITH-library vs BASE,从没比过:

1. **WITH-原始脚本检索**:gate 过的 raw final_script 直接做检索给 agent(不聚合)。
   这是"聚合有没有用"的关键对照——如果它和 WITH-library 打平,聚合的价值就只剩
   standalone 侧。
2. **WITH-最佳单脚本 vs WITH-merged-skill**:同 hint 格式只换内容,2-3 个模板 ×
   held-out 各三臂(merged / best-single / base),每臂 4-6 solve,一两小时出结果。

两种结果都有价值:赢了,"为什么要聚合"从信念变成表格;打平,是真实研究发现
(agent 强到不需要聚合 ⇒ 价值集中在 standalone / 重复归零侧,叙事要调整)。

## 当前立场(initial release 的口径)

- agent 有用:有数字(WebArena),但那是 reference 级的功劳,不能拿来证明 skill 本身对
- standalone:有三方一致 + 重放关兜底,是差异化本体("programs not notes")
- 聚合:机制论证 + 个案实锤(fallback/参数),受控对照欠着
- 所有对外文案已按此口径收敛;上面三条 backlog 按 分级入库 > ablation > README 诚实段
  的顺序慢慢还

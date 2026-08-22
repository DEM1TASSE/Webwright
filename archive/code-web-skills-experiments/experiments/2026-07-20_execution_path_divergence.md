# 同 template、不同执行路径:distillation 怎么处理 + 之前实验里到底有没有

**日期:** 2026-07-20
**问题:** 聚类按 **intent/template** 分组("what"),但 skill 是 **code**("how")。同一个 template 下 N 条 solve 的 `final_script.py` 执行路径可能不同 —— `evolve` 要把它们蒸成**一个** skill。会怎样?之前的实验里真出现过路径分叉吗?

## 结论
1. **现状是「赌能蒸出一条覆盖所有成员的路径,赌不中就整批 reject/reference」,没有"一个 template 多路径变体"的概念,replay 失败也不会重新拆分。**
2. **之前实验里确实有路径分叉,但是"风格分叉"(分解粒度/解析写法不同、共享同一条 UI 骨架),不是"导航分叉"(站点状态不同导致真的走不同步骤)。** 前者正是 distiller 最擅长调和的,所以能蒸成一个;真正的硬 case(弹窗有/无、A/B 布局、登录/免登)**这批数据里几乎不存在 → 未被压测。**

## `evolve` / `_refine` 实际怎么处理(`skill_factory/update.py`)
蒸馏 prompt(`_REFINE_SYS`)假设:「N 条解**只在参数值上不同**;相同的部分=骨架,不同的部分=参数」。执行路径不同**违反**这个假设。然后 `_replay` 把蒸出的**单个** skill 在**每条**成员 taskspec 上跑,必须都复现答案。三种结局:
- **路径差异是表面的**(同策略、不同值)→ 对齐成一条参数化脚本,replay 全过 → `grade=executable`。
- **路径真不同** → 单一路径在没覆盖到的实例上 replay 失败 → 喂 failure 修(`--verify-rounds`)→ 换一版重抽(`--draws`)→ 仍不行就 **reject**(或 `--on-fail reference`)。
- **`--verify off`**(update 默认)→ 不 replay,单路径脚本以 `grade=unverified` 直接入库,**没人检查它覆盖不覆盖所有成员**。

关键限制:
- **失败后从不回头改分组。** repair rounds / draws 都在**同一成员集合**上重试;`--draws` 只能救"蒸馏本身抽脆了",救不了"这批成员根本不该在一起"(两者失败长得一样,都是 replay fail)。
- **replay 是安全网,不是纠错器**:过度合并会被挡住(不发 executable),但不会自愈成两个 skill;诊断得人读 `.rejected_*.py` + 失败日志。
- **无兜底的是合并不足**(paraphrase 裂),会静默膨胀库。

## 之前实验里的路径分叉(实测)
同一 template 的多条解,结构差异很大:

**仓库 3 条训练轨迹**(`skill_factory/examples/trajectories/`,全是 "earliest nonstop flight"):
| 解 | 行数 | 函数数 | "最早"的选取方式 |
|---|---|---|---|
| sfo_bos | 132 | 4 | `choose_suggestion` 正则匹配机场名,无显式排序 |
| sea_jfk | 225 | 8 | `parse_visible_nonstop_rows` + `time_key` 按时间排 |
| lax_ord | 372 | 7 | `extract_cards`(最多 80 张)+ `to_minutes` 转分钟排 |

**Code-Web-Skills**(`experiments/data/outputs_flights/`,cheapest flight):行数 `103 / 141 / 143 / 394`,函数数 `2 / 3 / 4 / 26`(一条拆成 26 函数/394 行,其余 100 来行)。

**但定性是"风格分叉"不是"导航分叉":** literal cookie/consent 弹窗处理在几乎所有解里都是 **0**。三条走的底层 UI 步骤其实一样(开 flights → 设 one-way → 选机场 → 设日期 → 读结果),差的只是**分解粒度**和**解析/排序写法**。这属于"共享同一条 UI 骨架、代码风格不同",正是 `_REFINE_SYS`「identical=骨架,differing=参数」能调和的那种 —— 也解释了为什么 `learn --verify strict` 能一次过(~40% 首次通过)。

**推论:** 会让系统翻车的"导航分叉"(有的实例要关弹窗、有的不用;A/B 两版布局;要不要登录)**这批数据里不存在**,所以"同意图不同路径"这个担心**目前是未被真正压测的**。

## 设计选项(按成本)
- **A. 强化蒸馏 prompt(最便宜)**:明确告诉 distiller「N 条解可能走了**不同 UI 路径**,要**并集处理所有观察到的路径**(popup-或-无、selector-A-或-B、wait-for-任一),不是挑一条」。现在 `_REFINE_SYS` 只说 align+parameters,没说路径要 union。
- **B. 按执行路径二次聚类 → 多 variant(结构性根治)**:template 定"what",再在 template 内按 trajectory/脚本动作结构聚类,分出的簇各出一个 skill variant,运行时 try / 小 router 选。
- **C. 部分覆盖而非全或无**:一条路覆盖不了全部时,用最大可调和子集蒸一个 executable(覆盖主路径),异常路径实例留成单独 reference/variant。现在是整批拒。
- **D. 诚实降级到 reference**:路径方差大的 template 别硬发 executable,发 `grade=reference`(primitives+策略),让 agent 每次自己补最后一段路径。

**B 里那个"再聚类"可由 verification 驱动**:一个 group 反复 reject 时,给每成员各蒸一个 skill,交叉 replay(成员 i 的 skill 跑成员 j 的 taskspec)建 pass/fail 矩阵,按互相通过拆 sub-template。这把 replay 从 pass/fail 闸门升级成聚类信号。**当前未实现。**

## 待办
- [ ] 造**最小复现**:同 template,一条 `final_script.py` 含"关弹窗"分支、一条没有,答案相同,喂 `evolve --verify strict` —— 看它是调和成一条带 if 分支的鲁棒 skill,还是在没弹窗那条上 replay 失败被 reject。这才真正压测"导航分叉"。
- [ ] 若 A(prompt union)不够,再上 B(verification 驱动的路径再聚类)。
- [ ] 采/造带真导航差异的轨迹集(弹窗有无、A/B 布局、登录态),作为该问题的正式 benchmark。

## 关联
- 意图聚类(template 怎么分组,"what")见 [`2026-07-20_intent_clustering_tests.md`];本篇是它的下游("how":一个 template 内多条解怎么蒸成 skill)。
- 代码:`skill_factory/update.py`(`_REFINE_SYS` / `_refine` / `_replay` / `evolve`)、`learn.py`(`group_chunk`)。

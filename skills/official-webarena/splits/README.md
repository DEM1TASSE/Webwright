# 评测划分：设计与依据

对象：官方 WebArena `web-arena-x/webarena@dce04686`，812 题。
产物在本目录，生成脚本在 `../scripts/`，seed 一律 **42**。
每个主 JSON 带 `fingerprint` 字段，记录官方任务集、Verified 标注、以及两个生成脚本自身的 sha256 前缀——
同名文件悄悄漂移时可立即发现。

---

## 0. 为什么划分单位是 template 而不是 task

WebArena 的 812 题由 **190 个 `intent_template`** 实例化而来，同一模板的实例只有参数不同：

```
模板 4:  Open the thread of a trending post on the forum "{{subreddit}}" and subscribe.
  task595  subreddit=space          task598  subreddit=pittsburgh
  task596  subreddit=books          task599  subreddit=machine learning
  task597  subreddit=consoles
```

按 task 随机对半，`space` 会进 train、`pittsburgh` 进 test，**技能库在测试时见过几乎一模一样的题**。
这不是泛化，是记忆。所以凡是要测「未见过」的划分，单位必须是模板，且同模板实例不得跨边。

模板大小分布（这决定了后面每个预算选择的可行域）：

| 实例数 | 模板数 | 覆盖题数 |
|--:|--:|--:|
| 1 | 24 | 24 |
| 2 | 10 | 20 |
| 3 | 10 | 30 |
| 4 | 13 | 52 |
| 5 | 119 | 595 |
| 6 | 10 | 60 |
| 7 | 3 | 21 |
| 10 | 1 | 10 |
| **合计** | **190** | **812** |

绝大多数模板正好 5 个实例（119 个）。

---

## 1. 两种泛化半径，两种划分

留出的单位不同，划分方式就不同，不该强行统一：

| 层 | 留出单位 | 问的问题 | 需要折吗 |
|---|---|---|---|
| **T1 same-template** | 实例 | 见过该模板的 3 个示范，能解同模板的新参数吗 | 不需要 |
| **T2 cross-template** | 模板 | 完全没见过这个模板，技能库还有用吗 | 单次 50/50 |

T1 不需要折，因为同一个模板可以**同时**出训练实例和测试实例，不构成泄漏——
每个合格模板都能全额参与，一次跑完。
T2 必须整模板归边，所以是一次 50/50 划分。

两层的训练集**按设计就不一样**，这正是被操纵的变量。强行让它们一致，
等于把 T1 限制在 T2 恰好留在训练侧的那些模板上，为对称而丢掉一半数据。

**因此：不能直接比 T1 和 T2 的绝对分数。** 能比的是各自相对同测试集上 no-skill baseline 的提升。

---

## 2. T1 same-template（`same_template.json`）

```
for 每个模板:
    if 实例数 >= 4:                 # 3 个拿去训练后要留得下
        train += 模板内随机取 3      # seed 42
        test  += 其余全部
```

| | 题数 | 模板 |
|---|--:|--:|
| train | 438 | 146 |
| test | 300 | 146 |

**为什么随机取而不是取前 3。** 实例化顺序不是中性的：在 812 的 baseline 上，
每个模板的前 3 个实例通过率 **57.8%**，第 4 个起 **54.0%**——取头会让测试集
系统性比训练集难 3.8 点，按构造低估泛化能力。位置上没有单调趋势（第 2、3 位最高），
说明它是实例化顺序的偶然产物，正因如此随机取能消掉它：16 个 seed 下均值 **+0.17%**、
标准差 4.06%，与 0 相差 0.2 个标准误。

代价是单个 seed 抖动大（范围 −7.1% ~ +7.5%）。**不因此挑 seed**——按实测偏差选 seed
就是对着答案设计实验。seed 固定 42，实际难度差如实披露（见 §4）。

**为什么预算是 3。** 沿用本项目 `code/eval_webarena.py` 已有的 3 train / 2 held-out 约定。
固定数而非比例，是因为要问的是"固定 k 个示范能泛化多远"；
若问的是"示范越多越好吗"，才该用比例（脚本支持 `--budget 0.6`）。
预算越大测试集越小：预算 3 → test 300，预算 2 → test 约 460。

---

## 3. T2 cross-template（`cross_template.json`）

190 个模板按 **(site × task_type)** 分层，每层内**按模板大小降序、依次发给当前任务数较少的一侧**。
只按模板数交替发牌会让模板数齐、任务数歪（模板从 1 到 10 个实例不等）。

| | train | test | test 占比 |
|---|--:|--:|--:|
| 模板 | 93 | 97 | — |
| 题数 | 413 | 399 | 49.1% |

每站点、每 task_type 的 test 占比：

| 分层 | train 题 | test 题 | test 占比 |
|---|--:|--:|--:|
| Shopping | 95 | 92 | 49.2% |
| ShopAdmin | 92 | 90 | 49.5% |
| GitLab | 90 | 90 | 50.0% |
| Reddit | 56 | 50 | 47.2% |
| Map | 55 | 52 | 48.6% |
| Multi | 25 | 25 | 50.0% |
| retrieve | 163 | 156 | 48.9% |
| navigate | 58 | 55 | 48.7% |
| mutate | 192 | 188 | 49.5% |

### 两处标注问题（查过，非假设）

**`task_type` 有 5 个模板自相矛盾。** WebArena-Verified 逐 task 标注 retrieve/navigate/mutate，
但 `Buy the highest rated product ...`、`Add the following users ... as {{role}}`、
`Open an issue ...`、`Like/DisLike all submissions ...` 这 5 个模板里，
**同一操作的实例有的标 retrieve 有的标 mutate**。
模板取多数标签，再用 intent 起始动词的写守卫覆盖成 mutate。

这不是小事：这 5 个模板正是 6 个真写任务（723/726/783/789/792/793）被误标成只读的来源，
它们曾因此被调度进只读并行 lane。

**站点有 1 个模板不同质。** 模板 42「path and travel time from {{city1}} to {{city2}}」
两个实例只在 map、两个在 map+shopping_admin。T2 按实例站点的**并集**归类，归入 Multi。

**这个模板在 T1 里要单独标注。** T1 按实例随机划分，模板 42 的落点是
train = {758 (map), 759, 760 (map+shopAdmin)}、test = {757 (map)}。
这不是实例泄漏（参数不同），但测试实例的站点组成比训练实例更简单，
所以该题上的提升混入了一次站点组成的泛化。样本只有 1 题，对总数无实质影响，
但分析 T1 时应把 757 单列或剔除，不要当作纯参数泛化的证据。

**已核对**：verified 的 mutate 标注与本项目的 374 题 mutate 划分 **812/812 一致**，
所以 task_type 这个维度本身可信，噪声只在那 5 个模板的实例级标注上。

---

## 4. 划分的实际难度（用 812 inline baseline 测，供解读时折算）

划分是在看结果之前按 seed 42 固定的；下表是事后测量，用于披露而非用于挑 seed。

| 集合 | 题数 | inline 通过率 |
|---|--:|--:|
| T1 train | 438 | 55.3% |
| T1 test | 300 | 57.7% |
| T2 train | 413 | 56.2% |
| T2 test | 399 | 55.4% |

---

## 5. 统计功效：能检出多大的提升

同一批 438 题跑两次（中间改过 prompt 与若干 harness 修复）的任务级对照：

```
一致 346 (79.0%)    不一致 92 (21.0%)
旧过新挂 41         旧挂新过 51        净 +10 题 (+2.3 点)
McNemar p = 0.348   不显著
```

**21% 是端到端的观测不一致率，不是纯随机噪声。** 这两次运行之间 prompt 改过、
harness 修过若干缺陷，所以它混合了 agent 自身的随机性与系统改动，只能作为
"重复一次整条流水线会有多少题翻转" 的上界，不能等同于方差下限。
真正的噪声地板要用**完全相同的系统跑两遍**才测得到，本轮没有这个数据。

代入配对检验（80% power, α=.05）：

| 测试集 | 题数 | MDE |
|---|--:|--:|
| T1 test | 300 | 7.4% |
| T2 test | 399 | 6.5% |

低于这个量级的提升，样本量再大也难以显著（翻倍样本只换来约 1.7 点灵敏度）。
注意这些 MDE 用的是上界不一致率，真实噪声更低时 MDE 也会更小——
所以第一件该做的事是测出真正的噪声地板（同系统重跑两遍），而不是照这张表下结论。
可行的应对，按性价比：

1. **降噪声而非加样本**——把不一致率从 21% 压到 10%，MDE 直接减三成，比翻倍样本有效且便宜
2. **报效应量 + 置信区间**，不要二元显著性
3. **每题多次运行取多数**，压掉 agent 自身随机性
4. **换更敏感的指标**（步数、token、部分匹配），二元通过率丢信息太多

---

## 6. 文件

```
same_template.json                 T1：train/test ids、参与的模板、预算、seed
same_template_{train,test}_ids.json
cross_template.json                T2：train/test ids、模板列表、每模板的 site/type/n
cross_template_{train,test}_ids.json
README.md                          本文
../scripts/make_same_template_split.py    T1 生成脚本
../scripts/make_cross_template_split.py   T2 生成脚本
```

两个脚本默认输出到本目录，seed 一律 42，原地重跑即复现。
它们要读官方任务集与 WebArena-Verified 的标注，路径可用环境变量覆盖：

```
WEBARENA_HARNESS_ROOT   含 webarena_official/ 与 partition/ 的目录（默认 /data/ww_official）
WEBARENA_VERIFIED_JSON  webarena-verified.json 的路径（仅 T2 需要，用于 task_type 分层）
```

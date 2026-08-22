# 意图聚类(template aggregation)基础测试 + 设计记录

**日期:** 2026-07-20
**模型:** gpt-5.4(gateway phyagi)。5.5 会掩盖问题,固定用 5.4 测。
**被测:** `webwright.skill_factory.learn.group_chunk` —— learn 里「把多条 solve 按 template 聚类」那一步。
**脚本:** [`2026-07-20_intent_clustering_test.py`](2026-07-20_intent_clustering_test.py)(只需 webwright venv + gateway 三件套环境变量;不碰浏览器、不落库)。

## 结论
按一致规则重标 gold + 硬化 grouping prompt 后:**BASELINE 17/24 → HARDENED 24/24**(draw-case,gpt-5.4,每 case 3 draws,满分)。硬化版相对 baseline 修好三处:
- **filter 被当成 intent**(constraint_as_param):baseline 0/3(把"带私浴/近 Moscone"裂成 3 个),硬化 3/3;
- **跨站不分**(cross_site):baseline 0/3(Amazon/eBay 合并),硬化 3/3;
- **paraphrase 抖动**:baseline 2/3,硬化 3/3。
- 其余(objective 分、action 分、search/compare/recommend 分、背景噪声合)两版都 3/3。

## 关键决定(2026-07-20):objective 是 intent,不是参数
之前 gold 出过冲突:同样是「选择/优化标准不同」,flight 的 cheapest/fastest/fewest-stops 标了 merge,laptop 的 cheapest/best-rated 标了 split —— 自相矛盾。**定稿:不同 optimization objective / ranking criterion = 不同 template(split)。** 理由和「skill 是站点专属 code」自洽:cheapest 读价格、fastest 读时长、fewest-stops 读经停,**sort 依据和抽取字段都不同,本就是不同程序**。据此:
- 同一 objective 换措辞(cheapest = lowest-priced = least expensive)→ **merge**(paraphrase);
- 不同 objective(cheapest / fastest / fewest-stops / best-rated)→ **split**;
- **filter**(缩小候选集:私浴、近地标、价格上限)→ **参数 / merge**(不改 objective、不改 output schema)。

## 方法
Contrastive:每个 case 只变**一个语义因子**,标注该 merge 还是 split。打分**基于划分、与命名无关**:对每一对任务检查「模型同组 == gold 同组」,全对才算这一 draw 通过;掉/重 index 直接判失败。baseline(现行 prompt)vs hardened(现已进 `learn.py`)A/B,各 3 draws。

## 结果(gpt-5.4,每 case 3 draws)

| kind | case | BASELINE | HARDENED | 说明 |
|---|---|---|---|---|
| merge | paraphrase_merge | 2/3 | **3/3** | 同 objective 换措辞 → 一个 |
| merge | background_noise_merge | 3/3 | 3/3 | "去 SF 参加 Startup School…" 背景不干扰意图 |
| split | objective_split | 3/3 | 3/3 | cheapest / fastest / fewest-stops → **各一个 skill** |
| merge | constraint_as_param_merge | **0/3** | **3/3** | filter(私浴 / 近 Moscone)是**参数** |
| split | verb_object_split | 3/3 | 3/3 | cheapest vs best-rated(不同 objective)→ 分 |
| split | action_split | 3/3 | 3/3 | search / book / cancel → 分 |
| split | cross_site_split | **0/3** | **3/3** | Amazon vs eBay → 分(不同站=不同 skill) |
| split | search_compare_recommend_split | 3/3 | 3/3 | 检索 / 比较 / 推荐 → 分 |
| | **合计** | **17/24** | **24/24** | |

(注:objective gold 从 merge 翻成 split 后,baseline 也"被动答对"了这条 —— baseline 本就倾向把 objective 拆开,所以从上一版 14/24 升到 17/24;真正的差距在 filter、跨站、paraphrase 三处。)

## skill 边界规则(gold 可推导,不靠拍脑袋)
两任务同一 skill ⟺ **同一个参数化程序、在同一站点、能服务两者且产出相同 output schema**。
- **参数**:entities / values / **filters** / preferences / output 措辞层。
- **skill 身份(→ split)**:target **site**、core **action**(retrieve/create/modify/delete/compare/recommend)、**optimization objective**、**output schema**。

硬化 `_GROUP_SYS` 就是这条规则的落地(merge 三类 / split 四类 + canonical 措辞 + 已有 template verbatim 复用)。

## 意图聚类 edge case 的三桶优先级
输入现状是「已 solve 的 webwright 任务串」(多为明确祈使句):
- **桶 1(本测试覆盖):** paraphrase、filter-as-param、objective-split、site-split、action-split、search/compare/recommend、背景噪声。✅ 已 24/24。
- **桶 2(需「动作型 skill」支持后才有意义):** book/cancel/modify 有副作用、无稳定 answer、**不能 replay**,当前 gate+replay 模型 handle 不了 → 聚类器分开它们有前瞻价值,但别急着让系统 learn。
- **桶 3(上游 NLU,等输入变成聊天原话再管):** negation("don't book")、历史 vs 当前、hypothetical、句中改主意、指代歧义、"can you" vs "can I"、mentioned vs requested、主 vs 辅 intent。当前任务串里几乎不出现。

## granularity 与 replay 的现状(别误解)
- **合并不足(paraphrase 裂)**:无兜底,静默膨胀库 → 靠 prompt 硬化 + 增量命中已有 template 缓解。
- **过度合并(该拆的合了)**:replay 能**挡住**(蒸出的 skill 服务不了两成员 → verify 失败 → 不入库),但**不能自愈** —— 失败后只在同一分组上重试(repair rounds / draws),从不回头拆分;最终 reject / reference。
- **要「replay 决定 granularity」成真**,需补一个 verification 驱动的再聚类(reject 时给每成员各蒸一个 skill,交叉 replay 建 pass/fail 矩阵,按互通过拆 sub-template)。**当前未实现。**

## 稳定性指标(后续 benchmark 用)
1. Paraphrase consistency = 最大簇 / 总 paraphrase 数;
2. Contrastive separation = 近义不同意图 pair 被分开的比例;
3. Granularity consistency = 连续加 constraint,cluster 名不乱裂。

## 待办
- [x] objective = intent(split);filter = 参数;site = 身份 —— 已定,已进硬化 prompt。
- [x] 修跨站盲点 —— 硬化 prompt 显式「不同站=不同 skill,never a param」,cross_site 0/3 → 3/3。
- [ ] 扩 contrastive 集:output-format-as-param、scope/recipients-as-param、granularity 连续加 constraint 的稳定性(第 3 指标)。
- [ ] (backlog)两阶段 canonicalize→group-by;桶 2 动作 skill 的验证模型;replay 驱动的再聚类。

## 关联改动(尚未 commit)
- 硬化版 `_GROUP_SYS`(objective-split / site-identity / filter-param 版)已进 `webwright` 的 `src/webwright/skill_factory/learn.py`(`webwright-fresh-quickstart` 工作区,skill-library 分支,**未提交**)。
- 沿用 phyagi gateway(endpoint 需 `/responses` 后缀)。

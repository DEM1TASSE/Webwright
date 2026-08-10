# Online-Mind2Web 五站点 pilot 详细报告

## 1. 如何阅读结果

本报告区分三个概念：

- `from scratch`：不提供 primitive library，直接运行 Webwright agent。
- `routed / with-library`：任务先进入带 library 的 router，再由 metadata gate 决定是否选
  primitive。
- `with skill`：只有 metadata gate 实际选择了 primitive，且 agent prompt 中注入了对应
  primitive，才算真正的 skill treatment。

因此，`routed=1` 不等于 `with skill=1`。本次 pilot 中三个可运行 held-out 的 metadata
gate 均选择 `skip`，所以真正的 `with skill` 样本数是 **0**。Routed arm 随后安全回退到
普通 agent；它与 scratch 的差异来自独立运行的随机性和网页状态，不能归因于 primitive。

评测统一使用官方 Online-Mind2Web WebJudge，模型为 `o4-mini`：

- `1`：WebJudge 判定成功。
- `0`：WebJudge 判定失败。
- `null`：没有可供 WebJudge 判断的 final artifact，不能伪装成一次 Judge failure。

## 2. Held-out：from scratch 与 routed/with-library

| 站点 | Held-out task | From scratch | Routed/with-library | 实际使用 primitive | 解释 |
| --- | --- | --- | --- | --- | --- |
| Recreation.gov | `6174e5...`：找 Nashville 附近可骑马的 day-use park | **1**，15 calls | **1**，16 calls | 否，gate skip | 两个 arm 都找到 Cook Day Use Area；library 只会进入已知 facility 和打开详情 tab，不负责主要的地点/activity 搜索 |
| AKC | `eb2db4...`：找 energetic、hairless、medium barking 的犬种 | **1**，14 calls | **1**，16 calls | 否，gate skip | Scratch 正确使用 Hairless/Medium filter 后得到无匹配；routed 的独立 agent run 找到 American Hairless Terrier。两者都被 WebJudge 接纳，但差异不是 skill 效果 |
| BBB | `0b838c...`：找纽约 25 miles 内排名第二的 used-car dealer 的全部 locations | **0**，17 calls | **null**，17 calls 后无 final artifact | 否，gate skip | Scratch 只完成搜索、距离过滤和 rating 排序，未打开第二名并列出全部 locations；routed 也未完成且没有 judgeable artifact |
| Healthline | `64b761...`：比较两个 pescatarian diets | 未运行 | 未运行 | 不适用 | 只有 1 个 source 通过准入，未达到两 source-family 建库门槛 |
| The Weather Network | `2207bb...`：查询 Calgary 当前风速 | 未运行 | 未运行 | 不适用 | 2 个 source 中只有 1 个通过 WebJudge，未达到建库门槛 |

### Recreation.gov 的具体回答

两个 arm 均回答 Cook Day Use Area（J Percy Priest Lake，Near Hermitage, Tennessee）。轨迹
验证了：

- 搜索结果将其标为 `DAY USE`，距 Nashville 搜索中心约 11 miles。
- Facility 页面说明 J. Percy Priest Lake 距 downtown Nashville 约 10 miles。
- Recreation 文本明确列出 `horseback riding`。

WebJudge：scratch `1`，routed `1`。由于 gate 未选择 primitive，结论只能是“routed 回退没有
造成回归”，不能声称 skill 提升。

### AKC 的具体回答

- Scratch：选择 `Regular Exercise`（站点没有精确的 Energetic filter）、`Hairless`、
  `Medium`，页面显示无匹配结果。OM2W Judge 规则允许“正确执行过滤但无结果”被判成功。
- Routed/with-library：独立 run 使用 `Hairless` 和 `Medium` filter，再从 breed detail 验证
  energetic，回答 `American Hairless Terrier`。

WebJudge：scratch `1`，routed `1`。由于没有 primitive retrieval record，且 metadata gate
选择 skip，不能把 routed 找到具体犬种归因于 AKC library。

### BBB 的具体失败原因

Scratch 已完成：

1. 搜索 used car dealer。
2. 设置 `< 25 Miles`。
3. 按 Rating 排序。

但没有完成：

4. 打开排名第二的 Manhattan Motorcars, Inc.。
5. 查找并列出该 dealer 的所有 locations。

WebJudge 原因摘要：过滤和排序正确，但关键点 4、5 缺失，因此判为 `0`。Routed arm 的
library 只有 overlay dismissal，metadata gate 认为对核心搜索、排名和 location enumeration
帮助过小而跳过；之后 agent 达到调用上限，未产生 final artifact。

## 3. Source admission 逐任务结果

| 站点 | Task ID | Source family | WebJudge | 失败或准入说明 |
| --- | --- | --- | ---: | --- |
| Recreation.gov | `52efbab5...` | `mobile_app_lookup` | 1 | 通过 |
| Recreation.gov | `246d654f...` | `review_filter_and_sort` | 1 | 通过 |
| Recreation.gov | `73d08420...` | `facility_policy_lookup` | 1 | 通过 |
| AKC | `c03ee2be...` | `service_marketplace_groomer_pricing` | 1 | 通过 |
| AKC | `f2be37a9..._110325` | `event_search_obedience_trial` | 1 | 通过 |
| AKC | `b3a7da96...` | `breed_comparison` | 0 | 只选择了 Afghan Hound、Akita、Azawakh，没有点击 Compare Breeds，也没有展示实际 side-by-side comparison |
| BBB | `7be8cd8d...` | `local_business_search` | 1 | 通过 |
| BBB | `3ec0f613...` | `accreditation_information` | 1 | 通过 |
| BBB | `60cbbbd5...` | `scam_phone_lookup` | 1 | 通过 |
| Healthline | `301f267f...` | `recipe_search_with_constraints` | null | CloudFront 403，未产生 final artifact |
| Healthline | `dcd26e66...` | `weight_management_quiz` | null | CloudFront/站点执行阻塞，达到调用上限且无 final artifact |
| Healthline | `5c00e956...` | `drug_dosage_content_lookup` | 1 | 通过；Vivitrol 推荐剂量查询成功 |
| The Weather Network | `871e7771...` | `seven_day_forecast` | 1 | 通过 |
| The Weather Network | `f389398d...` | `climate_news_lookup` | 0 | 打开的是 Featured climate news，但没有使用或确认按 latest 排序，不能满足“latest”要求 |

总计：14 个 source，12 个可判定，10 个通过 WebJudge。Healthline 的两条 `null` 是站点或
执行基础设施问题，不计作 WebJudge `0`。

## 4. 生成的 primitive library

Library 已随本报告提交，位于 [`libraries/`](libraries/)。它们保持运行时需要的原始
`.primitives/<site>/catalog.json` 和 Python code 布局。

### Recreation.gov

路径：[`libraries/recreation_gov/`](libraries/recreation_gov/)

| Primitive | 能力 | Source 支持 |
| --- | --- | --- |
| `recreation_gov/navigate_to_facility_detail` | 从 Recreation.gov 搜索/建议结果进入指定 facility 或 campground detail | `facility_policy_lookup`、`review_filter_and_sort` |
| `recreation_gov/open_facility_detail_tab` | 在 facility detail 打开 Rules、Ratings 等 tab，并验证内容 | `facility_policy_lookup`、`review_filter_and_sort` |

Held-out 的主要难点是先按地点与 activity 找到正确公园。已有 primitive 的前置条件是已经
识别 facility，因而 gate 判断它们没有覆盖主要工作。

### AKC

路径：[`libraries/akc_org/`](libraries/akc_org/)

| Primitive | 能力 | Source 支持 |
| --- | --- | --- |
| `akc_org/dismiss_cookie_banner` | 在 AKC 页面关闭 cookie banner | `event_search_obedience_trial`、`service_marketplace_groomer_pricing` |
| `akc_org/navigate_akc_destination` | 通过站点 link 或官方 fallback URL 进入 AKC 子页面 | `event_search_obedience_trial`、`service_marketplace_groomer_pricing` |

Held-out 需要 breed trait filter 和 breed matching；现有 primitive 只有 cookie 和目的地导航，
对核心任务覆盖不足，因此 gate skip。

### BBB

路径：[`libraries/bbb_org/`](libraries/bbb_org/)

| Primitive | 能力 | Source 支持 |
| --- | --- | --- |
| `bbb_org/dismiss_site_overlays` | 关闭 BBB cookie consent 和 notification overlays | `scam_phone_lookup`、`local_business_search`、`accreditation_information` |

Held-out 需要搜索、距离 filter、rating sort、选择第二名和枚举 locations。关闭 overlay 只是
边缘帮助，gate skip 是合理的保守决策。

## 5. 为什么本次没有真正的 with-skill 分数

Primitive retrieval record 只在 metadata gate 决定 `use` 或 `adapt` 后写出。本次三个 eligible
held-out 均没有生成 retrieval record，并在 routed console 中显示 primitive stage skip，之后
进入 scratch fallback。

因此本次可报告：

- Scratch success：Recreation `1`、AKC `1`、BBB `0`。
- Routed pipeline success：Recreation `1`、AKC `1`、BBB `null`。
- Primitive treatment coverage：`0 / 3 = 0%`。
- With-skill success：没有样本，不能计算。
- Safe-skip：Recreation 与 AKC 在 skip 后仍成功。

不能报告“with skill 2/2 成功”，因为这会把 routed fallback 错写成 skill treatment。

## 6. 失败类型总结

| 类型 | 数量/案例 | 含义 |
| --- | --- | --- |
| Source answer failure | AKC breed comparison、Weather climate news | Agent 有轨迹，但缺失任务关键动作/证据，被 WebJudge 正确拒绝 |
| Site/infrastructure blocker | Healthline 两条 source | CloudFront 403 或执行阻塞，没有 judgeable artifact |
| Library admission不足 | Healthline、Weather | 只有一个 admitted family，不允许建库 |
| Primitive gate skip | Recreation、AKC、BBB held-out | Primitive 对 held-out 核心能力覆盖不足 |
| Held-out answer failure | BBB scratch | 只完成 filter/sort，未完成第二名的所有 locations |
| Held-out no artifact | BBB routed fallback | 达到调用上限，未生成可判定 final run |

## 7. 可复现信息

- Dataset SHA-256：`7dedf381531d423dc0fc48d21dc1d425655dd75f38b10211a880fa09102f257f`
- Upstream evaluator commit：`f0d805ee0e9e0b3ea70911e45e5264b72968f3dc`
- Judge model：`o4-mini`
- Judge score threshold：`3`
- Frozen split：[`manifest.json`](manifest.json)
- Machine-readable summary：[`results.json`](results.json)
- 完整原始运行 artifact 位于本机 `/home/t-demiwang/om2w-pilot-5sites`；其中包含 screenshots
  和完整 WebJudge prompts，体积较大且没有全部提交到 Git。


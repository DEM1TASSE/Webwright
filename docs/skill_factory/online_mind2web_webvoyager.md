# Online-Mind2Web 现状与 WebVoyager 任务调研

更新时间：2026-08-10

## 总结

Online-Mind2Web（OM2W）接入已经端到端跑通：Webwright 可以在真实网站上执行任务，
将轨迹转换成官方 evaluator 所需格式，使用上游 WebJudge 作为答案准入 gate，基于通过
WebJudge 的 source run 构建同站点 primitive catalog，再通过 routed 路径运行 held-out
任务。

冻结的五站点 pilot 验证了整条 pipeline，但尚未测出 primitive 带来的提升。三个站点
成功建立了合格的 primitive library，然而所有 held-out 任务都被 primitive metadata gate
判定为 `skip`，原因是生成的 primitive 没有覆盖 held-out 任务中足够实质性的能力。

WebVoyager 更适合作为验证“能否学习并复用 primitive”的开发集。它的官方数据包含 643
个任务，但只有 15 个站点，每站 41--46 个任务；OM2W 则是 300 个任务、136 个站点。
WebVoyager 因此可以构造同站点、同 capability、不同实例的 train/held-out split。

但 WebVoyager 不应完全替代 OM2W：其任务更旧，部分任务依赖日期和实时内容，原始 evaluator
和任务维护也弱于 OM2W。推荐分工如下：

1. 用 WebVoyager 测 primitive treatment、成功率提升和效率收益。
2. 用 OM2W 测真实网站鲁棒性、答案 gate 准确性、primitive 安全跳过以及外部泛化。

## 1. Online-Mind2Web 当前情况

### 1.1 Benchmark 特征

官方 OM2W 包含 300 个真实在线任务，覆盖 136 个网站。项目方会更新因网页变化、CAPTCHA
或其他原因而失效的任务。

WebJudge 的评测分为三个概念阶段：

1. 识别完成任务必须满足的关键点。
2. 从轨迹中选择关键截图。
3. 根据任务、关键点、截图和 action history 判断结果。

官方仓库报告，使用 o4-mini 的 WebJudge 与人工判断的一致率为 86%，成功率差距为 3.8
个百分点。

主要来源：

- [Online-Mind2Web 官方仓库](https://github.com/OSU-NLP-Group/Online-Mind2Web)
- [Online-Mind2Web leaderboard](https://hal.cs.princeton.edu/online_mind2web)

### 1.2 当前分支已有实现

分支 `dev-online-mind2web-gate` 包含：

| 组件 | 路径 | 用途 |
| --- | --- | --- |
| 官方 evaluator adapter | `src/webwright/skill_factory/om2w_eval.py` | 转换 Webwright 轨迹并调用 OM2W 上游 evaluator |
| Answer/admission gate | `src/webwright/skill_factory/gate.py` | 只允许 WebJudge 接纳的 source run 进入学习阶段 |
| 单任务 paired runner | `evals/om2w/smoke_pipeline.py` | 运行 scratch/routed、物化 verdict 并比较结果 |
| Primitive builder | `evals/om2w/build_generated_primitives.py` | 从通过 WebJudge 的 source family 建立站点 catalog |
| Primitive catalog/retrieval | `src/webwright/skill_factory/primitive_catalog.py`、`primitive_retrieve.py` | 存储 primitive，并通过 metadata-only gate 选择 treatment |
| 冻结 pilot split | `evals/om2w/pilot_5sites/manifest.json` | 在运行前固定 source 和 held-out ID |
| Pilot 结果 | `evals/om2w/pilot_5sites/results.json` | 记录结果以及是否真正发生 primitive treatment |

Pilot 使用的数据和 evaluator：

- 数据集：`Online_Mind2Web.json`，300 个任务。
- 数据集 SHA-256：`7dedf381531d423dc0fc48d21dc1d425655dd75f38b10211a880fa09102f257f`。
- 上游 evaluator commit：`f0d805ee0e9e0b3ea70911e45e5264b72968f3dc`。
- Judge：`o4-mini`，准入阈值为 3。
- 完整运行产物：`/home/t-demiwang/om2w-pilot-5sites`。

### 1.3 五站点 pilot 结果

Pilot 冻结了 Recreation.gov、AKC、BBB、Healthline 和 The Weather Network 上的 14 个
source 任务及 5 个 held-out 任务。

| 站点 | Source 计划数 | 可判定 | 通过准入 | Active primitives | Held-out scratch | Held-out routed | 使用 primitive？ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Recreation.gov | 3 | 3 | 3 | 2 | 1 | 1 | 否；metadata gate 跳过 |
| AKC | 3 | 3 | 2 | 2 | 1 | 1 | 否；metadata gate 跳过 |
| BBB | 3 | 3 | 3 | 1 | 0 | 未产生 final artifact | 否；metadata gate 跳过 |
| Healthline | 3 | 1 | 1 | 0 | 未运行 | 未运行 | Library 不满足准入条件 |
| The Weather Network | 2 | 2 | 1 | 0 | 未运行 | 未运行 | Library 不满足准入条件 |

汇总：

- 14 个 source 中有 12 个可以交给 Judge。
- 12 个可判定 source 中有 10 个通过 WebJudge。
- 5 个站点中有 3 个达到“至少两个通过准入的 source family”要求。
- 两个 held-out pair 的两个 arm 都产生了 verdict，结果均为 `scratch=1, routed=1`。
- 没有任何 held-out 任务真正使用 primitive，因此不能计算 primitive effect size。

`routed=1` 只表示任务进入 routed pipeline 后，其最终答案通过了 WebJudge；它不表示
primitive 被选择。正式 treatment 分析必须同时记录答案 verdict 和
`primitive_treatment=true|false`。

### 1.4 Primitive metadata gate 为什么全部 skip

Source WebJudge gate 和 held-out primitive gate 是两道不同的 gate：

1. WebJudge 判断 source trajectory 是否成功、是否值得用于学习。
2. Primitive metadata gate 判断已有 primitive 是否能实质性帮助当前 held-out 任务。

Metadata gate 的规则要求：如果获得 primitive 所需前置状态本身就是任务的主要工作，或
primitive 只能提供边缘帮助，就应当选择 `skip`。

| 站点 | 学到的能力 | Held-out 能力 | Skip 原因 |
| --- | --- | --- | --- |
| Recreation.gov | 进入已知 facility 页面；打开 facility detail tab | 根据 activity 和 location 搜索并识别公园 | 搜索和实体选择仍是主要工作 |
| AKC | 关闭 cookie；跳转到 AKC 子页面 | 根据 energetic、hairless、barking 等 trait 选择犬种 | 没有 breed selector 或 trait filter primitive |
| BBB | 关闭反复出现的 overlay | 搜索 dealer、选择排名第二的结果、列出所有 locations | 关闭 overlay 对核心任务帮助过小 |

Pilot 使用了完全不同的 source family 和 held-out family，同时 builder 又要求 primitive
必须得到多个已准入 source family 的支持。多个 family 的交集自然容易退化成通用导航、
tab 和 overlay 操作。Held-out 又来自另一个 family，于是 gate 没有理由选择它们。

因此 gate 本身不是主要问题；问题是 split 与预期复用能力没有对齐。

### 1.5 已发现的运行问题

- Healthline 在两个 source 任务中返回 CloudFront 403。这属于站点基础设施失败，不应算作
  agent 或 WebJudge 失败。
- 多个 Webwright child process 在写出 final artifact 后仍未退出。Pilot 只能先验证
  artifact 完整，再手动结束等待中的 parent process。批量运行需要明确的 post-final
  exit/timeout 策略。
- Routed execution 必须显式获得 `SKILL_MODEL_ENDPOINT`、`SKILL_MODEL_NAME` 和凭证。
  Browser agent 使用的 gateway YAML 不会自动配置 primitive router。缺少这些环境变量时，
  router 可能回退到默认 OpenAI endpoint 并返回 401。
- Routed arm 可能安全回退到 scratch。报告必须区分 routed pipeline 和真正的 primitive
  selection，建议强制记录 `route_stage`、`route_decision`、primitive ID 和 content hash。
- OM2W 每站任务过少。只有两三个任务的站点难以同时组成多个 source family 和具有能力
  重叠的 held-out 集合。

## 2. WebVoyager 官方任务集

### 2.1 数据集与评测

官方 `data/WebVoyager_data.jsonl` 恰好包含 643 个任务。每条记录包括 `web_name`、`id`、
`ques` 和起始 `web`。配套的 `reference_answer.json` 按站点保存答案，其中很多答案标记为
`possible`，表示可能存在多个可接受答案，或答案会随实时网页变化。

以下统计和例子来自官方仓库 commit：
`5a7896738c10bfb8b9edccce6bb0e0411f8ae569`。

原始 evaluator 会把任务、agent 回答和最后若干张截图交给 GPT-4V。论文报告，在使用完整
trajectory 时，自动评测与人工判断的一致率为 85.3%。官方仓库明确指出 Booking 和
Google Flights 的任务具有时间敏感性，运行前需要手动更新日期。

主要来源：

- [WebVoyager 官方仓库和任务说明](https://github.com/MinorJerry/WebVoyager)
- [WebVoyager 论文](https://arxiv.org/abs/2401.13919)

### 2.2 精确站点分布与具体任务类型

| 站点 | 任务数 | 主要任务类型 | 官方任务例子 | Primitive 适配判断 |
| --- | ---: | --- | --- | --- |
| Allrecipes | 45 | Recipe 搜索、多条件过滤、详情、ingredients/instructions/nutrition 提取 | 查找满足评分和评论数约束的素食千层面；查找准备时间低于阈值的 cauliflower crust 并报告 calories | **高**：重复的 search-filter-detail-extract 流程 |
| Amazon | 41 | 商品搜索、facet、价格/评分过滤、详情、比较、购物车 | 查找低于 50 美元的黑色 7 码跑鞋并加入购物车；查找指定价格区间且评论数超过 500 的键盘 | 机械复用性中等，但反爬、库存变化和购物车副作用风险高 |
| Apple | 43 | 产品规格、型号比较、配置选项、定价、support 内容 | 比较最新 MacBook Air 价格；查看 14 英寸 MacBook Pro 配置中的键盘选项 | 中高：导航和配置可复用，但产品和价格会变化 |
| ArXiv | 43 | 基础/高级搜索、分类/日期过滤、结果计数、论文详情、help 页面 | 比较 quantum computing 在 q-ph 和全部 archive 的结果数；查找最新 statistics ML 论文及其摘要 | **高**：页面结构稳定，query/detail 流程重复 |
| BBC News | 42 | Section 导航、最新文章、指定文章、总结 | 查找最新 Green Living 文章；找到指定 climate guide 并提取原因 | 中等：导航可复用，但 latest 和答案快速变化 |
| Booking | 44 | 地点/日期/人数输入、amenity filter、评分/排序、价格/币种 | 查找适合两人的巴黎酒店并要求免费取消；过滤伦敦酒店后统计结果数 | 首轮不推荐：原始日期大量过期且 availability 高度变化 |
| Cambridge Dictionary | 43 | 单词查询、英美发音、definition、example、grammar | 查询 sustainability 的定义和发音；查询 procrastination 的英美发音与例句 | **高**：大量密集的近模板实例，结构稳定 |
| Coursera | 42 | 课程搜索、level/duration/institution filter、课程详情、syllabus、review distribution | 查找持续 1--3 个月的 3D printing 初级课程；查看指定 Stanford 课程的星级占比 | **中高**：复用链路较强，但存在登录和 UI 漂移风险 |
| ESPN | 44 | 比分、赛程、standings、leaders、team/player detail、新闻 | 获取当前 NBA 东部排名；报告最近一场 NBA 比赛的得分王 | 中等：结构重复，但内容高度时间敏感 |
| GitHub | 41 | Repository qualifier 搜索、stars/update/language 过滤、repo 详情、contributors、文档 | 查找两天内更新且超过 500 stars 的 Python repo；查找 blockchain repo 并列出前五名 contributors | **高**：query 和 repo-detail primitive 可复用；应排除 signup 任务 |
| Google Flights | 42 | 出发地/目的地/日期、trip type、stops/airline filter、最便宜/最短排序 | 查找 NYC 到 Tokyo 的最低价往返航班；比较直飞价格和时长 | 低：日期过期、价格变化、UI 和地区差异明显 |
| Google Map | 41 | 地点/类别搜索、距离、评分/营业时间过滤、详情、评论 | 查找五个评分高于 4.8 的 Seattle salon；找 Brooklyn Bridge 附近 24 小时停车场并总结评论 | 能力复用性中高，但 consent、地区和结果不确定性较强 |
| Google Search | 43 | 事实查询、体育、排行榜、knowledge panel、开放搜索、少量登录任务 | 查询电影上映日期；查询 Phoenix Suns 最近比赛得分 | 对 primitive 学习较弱：入口浅，任务领域非常分散 |
| Hugging Face | 43 | Model/dataset/Space 搜索、task/library/language filter、排序、model card/docs | 查找 2023 年 3 月更新的 sentiment model；找下载最多的 en-zh 翻译模型并报告 metrics/usage | **高**：结构化 search-detail-documentation 流程重复 |
| Wolfram Alpha | 46 | 结构化 query、result pod、数学和科学计算 | 计算定积分；求解微分方程；查询指定地点和日期的地磁场 | Query/result primitive 复用性高，但更偏 query formulation 而非复杂导航 |

总数为 643。各站点任务数为 41--46，与论文中“每站约 40--45 个任务”的描述基本一致；
正式发布数据中的 Wolfram Alpha 有 46 条。

### 2.3 Template 与 cross-template 分布（粗略分析）

WebVoyager 官方没有提供 template 或 capability-family 标签。以下分类是调研得到的启发式
taxonomy，不是数据集原生标注。

分析使用了两个视角：

1. 人工查看任务实际要求的操作骨架。
2. 保守的词汇近似检查：归一化引号中的实体和数字，移除常见 instruction words，然后
   计算每个任务与同站点其他任务之间最大的 token-Jaccard similarity。

词汇相似度只能识别明显的近模板。Amazon、Booking、Maps 等任务中的实体和日期通常没有
引号，会显著降低分数。因此这张表只能视为近模板数量的下界，不能直接当 cluster label。

#### 词汇近模板下界

| 站点 | 任务数 | 最佳匹配相似度中位数 | 最佳匹配 >= 0.35 | 最佳匹配 >= 0.50 |
| --- | ---: | ---: | ---: | ---: |
| Allrecipes | 45 | 0.38 | 28 | 7 |
| Amazon | 41 | 0.17 | 0 | 0 |
| Apple | 43 | 0.25 | 12 | 8 |
| ArXiv | 43 | 0.24 | 6 | 0 |
| BBC News | 42 | 0.27 | 6 | 0 |
| Booking | 44 | 0.27 | 7 | 0 |
| Cambridge Dictionary | 43 | 0.57 | 31 | 25 |
| Coursera | 42 | 0.23 | 8 | 2 |
| ESPN | 44 | 0.27 | 16 | 12 |
| GitHub | 41 | 0.38 | 24 | 10 |
| Google Flights | 42 | 0.33 | 18 | 3 |
| Google Map | 41 | 0.22 | 4 | 2 |
| Google Search | 43 | 0.12 | 4 | 0 |
| Hugging Face | 43 | 0.26 | 12 | 4 |
| Wolfram Alpha | 46 | 0.12 | 0 | 0 |

#### 人工操作骨架判断

| 分布类型 | 站点 | 粗略解释 |
| --- | --- | --- |
| 单一重复骨架占主导 | Allrecipes、Amazon、Booking、Google Flights、Google Map、Wolfram Alpha | 约四分之三或更多任务重复同一个 form/search-result-detail 流程，主要变化是实体和约束 |
| 一个主 family 加少量旁支 | Cambridge Dictionary、Apple、BBC News、ESPN | 多数任务重复 lookup/detail 或 section/detail，其余涉及 grammar、配置、排名、游戏、support 或 marketing 页面 |
| 多个相互连接的 family | ArXiv、Coursera、GitHub、Hugging Face | Search、filter、entity detail 和 documentation 是不同 template，但由可复用的中间导航能力连接 |
| 入口相同但目标高度异质 | Google Search | 多数任务只共享“发起一次搜索”，后续领域和证据需求差异很大 |

逐任务查看后，几个重点站点大致如下：

- **Allrecipes：**45 个任务中约 41 个属于 recipe discovery/detail extraction。区别主要是
  ingredients、instructions、time、ratings、reviews、nutrition、storage 和 latest review
  等输出字段。这更像同模板参数变化，而非真正的跨模板迁移。
- **Cambridge Dictionary：**约二十多个任务是单词查询，再组合 definition、英美发音、
  IPA、meaning 和 example sentence。另有 8 个 grammar family，以及 translation、
  thesaurus、quiz/game、shop 和语言切换等小 family。
- **GitHub：**repository discovery/search 是最大 family。进入 repository 后，又分支到
  contributors、releases、commits、changed files、issues、wiki、README、language、stars
  和 forks。Pricing、Copilot、Skills、customer stories 和 signup 属于其他 family。
- **ArXiv：**最大连通部分包括 keyword/category/date/author/journal-reference search、结果
  计数、latest-category browse 和 paper detail。Help/policy、organization/blog、store/cart
  是独立 family。
- **Hugging Face：**model search/filter/rank 和 model-card extraction 是最大部分。其他
  family 包括 dataset、Spaces/inference、documentation、blog/daily paper、pricing 和组织内容。
- **Coursera：**course discovery/filter 和 named-course inspection 占主导。详情页又分成
  modules、duration、rating histogram、instructor、skills 和 reviews。Specialization、
  degree、partner、Plus/Business 等是相关但不同的 template。

#### 真正存在 cross-template transfer 的位置

最好的 cross-template 站点不一定是近重复最多的站点。更重要的是：不同最终任务之间存在
实质性的共享中间状态。

```text
GitHub repository search
  -> repository page
      -> contributors | releases | commits | issues | wiki | README

ArXiv query/category browse
  -> result list
      -> paper abstract | versions | HTML | PDF inspection

Hugging Face model search/filter
  -> model page
      -> metadata | model card | metrics | usage | linked Spaces

Coursera course search/filter
  -> course or specialization page
      -> modules | reviews | instructor | skills | included courses
```

这些关系适合 cross-template 实验，因为 held-out 的最终目标不同，但仍共享一个重要的中间
能力。它们不同于失败的 OM2W pilot：OM2W 中的共享 primitive 通常在 held-out 的主要工作
开始前就结束了。

相对而言：

- Allrecipes 和 Cambridge Dictionary 很适合做**同模板、不同参数**实验，但随机 split
  太容易发生 near-duplicate leakage。
- Booking 和 Google Flights 虽然模板重复很强，但日期过期和实时结果变化使其不适合首轮。
- Google Search 和 Wolfram Alpha 的主要难点是 query formulation 和答案提取。只学会输入
  query 的 primitive 可能减少步骤，但很难证明复杂网站技能复用。

### 2.4 这些任务对 primitive 学习意味着什么

WebVoyager 中有若干天然重复的 capability：

- **Search/filter/detail：**Allrecipes、Amazon、Coursera、GitHub、Hugging Face。
- **结构化 query/result extraction：**ArXiv、Cambridge Dictionary、Wolfram Alpha。
- **地点搜索、详情和评论：**Google Maps。
- **日期表单和排序：**Booking、Google Flights。
- **Section/latest/detail：**BBC、ESPN。
- **产品选择和配置：**Apple、Amazon。

这种任务密度允许我们将 task identity 与 capability 分开。例如，GitHub repository-search
primitive 可以用 climate 和 quantum query 训练，再用 blockchain query 做 held-out。实体、
日期、阈值和答案均未见过，但可复用 capability 仍然存在。

这种测试比随机 split 严格，又不像当前 OM2W pilot 那样把 held-out 换成完全无关的 family。

### 2.5 数据质量与泄漏风险

- 很多任务是近模板改写。随机切分会高估泛化能力。
- Reference answers 包含旧的评分、评论数、价格、排名、模型信息和 2023/2024 日期，不能
  直接作为当前 live web 的固定 gold answer。
- Booking 和 Google Flights 明确需要重写日期。必须先完成任务实例化，再冻结 split，并在
  manifest 中记录修改。
- 初始 read-only pilot 应排除 cart、signup、login 和 account 任务。
- `latest`、最高评分、价格、availability 和 review count 必须依赖 trajectory evidence 和
  live judge，不能只与旧 reference answer 做字符串匹配。
- Google Search 的任务很多，但站点操作深度很小，因此不适合验证 site primitive library。

## 3. 推荐的 WebVoyager primitive pilot

### 3.1 首批站点

先选择五个只读、capability 密集的站点：

1. ArXiv
2. Cambridge Dictionary
3. GitHub
4. Hugging Face
5. Allrecipes 或 Coursera，根据 live accessibility smoke test 决定

Wolfram Alpha 作为第一替补。首轮避免 Amazon、Booking 和 Google Flights。

### 3.2 Split 单位和准入规则

不能直接随机切分原始任务。应先为每条任务标注：

- `site`
- `capability_family`
- `entity_or_query`
- `constraints`
- `read_only`
- `time_sensitive`
- `requires_login`
- `live_validated_at`

每个站点先选择 20 个任务，至少覆盖三个 capability family：

- 12 个 source/train
- 8 个 held-out
- 每个被评测 capability 至少有两个 source 和两个 held-out
- 两个 arm 之间不能出现相同实体、query、答案或近重复措辞
- 必须存在 capability overlap，但不要求 template 完全相同

在运行前冻结 task ID、修改后的日期、family label、数据集 commit 和 judge 配置。

实验应明确拆成两条 track：

- **Within-template generalization：**操作骨架相同，但实体和约束不同。先证明 primitive
  机制本身确实能够工作。
- **Cross-template transfer：**最终任务目标不同，但预注册一个共享的实质性中间能力，
  例如 GitHub repository discovery 迁移到 release 或 issue inspection。

两条 track 不能合并成一个 headline number。Cross-template 是更强的主张，运行前必须记录
预期共享的 capability。

### 3.3 指标

需要分别报告：

- Source WebJudge admission rate。
- 达到最低准入 family 数的站点比例。
- Primitive build 的接受和拒绝数量。
- Primitive gate selection rate。
- Treatment coverage：`primitive_treatment=true` 的 held-out 比例。
- Scratch 和 routed 的 WebJudge success。
- 只在实际 treatment 任务上的成功率。
- Paired lift、regression、rescue 和 safe skip。
- Calls、tokens、wall-clock time 和站点基础设施失败率。

Primitive 主结果只能在真正选择了 primitive 的 paired task 上计算。全任务 routed success
可以作为系统安全指标，但不能作为 primitive effect estimate。

## 4. 结论

继续保留 OM2W 支持，但下一轮 primitive-learning pilot 应迁移到经过过滤的 WebVoyager
subset。理想证据链是：

```text
同站点、同 capability 的多个 source 实例
  -> WebJudge 通过的 source trajectories
  -> 跨实例 primitive
  -> metadata gate 在不同 held-out 实例上选择 primitive
  -> paired scratch/routed WebJudge 比较
```

当 WebVoyager 上出现非零 treatment coverage 后，再回到任务稀疏、难度更高的 OM2W 做外部
验证。如果在 capability-overlap 的 WebVoyager split 上仍然全部 skip，问题就不是 OM2W
任务密度，而是 primitive abstraction 或 routing 本身。

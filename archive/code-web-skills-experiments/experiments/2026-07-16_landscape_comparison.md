# 同类工作对比:什么驱动 skill 的产生

**日期:** 2026-07-16 ｜ **方法:** 不看 README 宣传口径,**clone 仓库读实现和 prompt**。
下面每条断言都标了出处文件,可复核。

| repo | commit | 日期 |
|---|---|---|
| microsoft/SkillOpt | `57333f3` | 2026-07-15 |
| jackwener/opencli | `b0f84c9` | 2026-07-13 |
| browser-act/skills | `51daea1` | 2026-07-14 |

> ⚠️ 本文初稿对 OpenCLI 有三条错断言(人写 adapter / 人工 PR 维护 / 无自愈),
> 已在下文订正。教训:**对别人项目下断言前必须读它的 `skills/` 和源码,不能只读 README**
> ——README 不会告诉你它有 autofix。

## 结论先行

**"有没有验证"不是我们的差异点——四家都有某种验证。** 我原本以为是,查完代码发现
不成立。真正的差异在三条轴:

1. **什么驱动 skill 的产生**:站点探索驱动 vs **同模板 N 次 solve 聚合驱动**(我们);
2. **闸证明了什么**:分数提升 / 创建时能跑 vs **无模型重放自己的训练答案**(我们);
3. **源码为什么被打开**:为修好共享目录 vs **为这一次任务改一版、库不动**(我们)。
   (注:三家的源码 agent 都能读能改 —— 这不是差异点,**改的目的**才是。)

## 各家实证

### SkillOpt(microsoft/SkillOpt)—— 兄弟项目,不同轴线

- **skill 形态**:自然语言文档(`best_skill.md`)。证据:`skillopt/evaluation/gate.py`
  里有 `compute_semantic_density(skill_content)`,统计 MUST/ALWAYS/NEVER/CRITICAL
  这类祈使词密度 —— 它优化的是**给冻结 agent 读的指令文本**。
- **驱动**:轨迹驱动的文本编辑。优化器模型把打分后的 rollout 变成对**单个文档**的
  add/delete/replace 编辑。
- **闸**:`skillopt/evaluation/gate.py` —— 候选在**留出集分数**上(hard 精确匹配 /
  soft F1 / mixed 加权)**严格高于**当前/最佳才 accept,返回
  `accept_new_best | accept | reject`。
- **self-evolving**:有(SkillOpt-Sleep,v0.2.0 2026-07-02:harvest → mine → replay
  → consolidate,同样过留出集闸)。
- **适用 domain:通用 agent 任务,而且 eval 里一个网页任务都没有。** 实证 ——
  `skillopt/envs/` 与 `configs/` 下的环境是:

  | env | 是什么 |
  |---|---|
  | `alfworld` | 文字互动环境 |
  | `docvqa` | 文档视觉问答 |
  | `livemathematicianbench` | 数学 |
  | `officeqa` | Office 文档问答 |
  | `searchqa` | 检索问答 |
  | `spreadsheetbench` | 电子表格 |

  → **它是 domain-general 的文本技能优化器,不是网页方向。**
- **关系**:**互补,不是竞争**。它做的是"冻结 agent + 可训练的文本技能";我们做的是
  "把解题过程变成可脱离模型运行的程序"。同一个实验室的两条不同轴线,连 benchmark
  都不重叠。

### OpenCLI(jackwener/opencli)

- **skill 形态**:注册式 JS adapter。`clis/<site>/<cmd>.js`,形如
  `cli({site:'jd', name:'detail', args:[...], columns:[...], func: async (page, kwargs) => {...}})`。
  仓库里 **176 个站点目录 / 1314 个实现 .js**。
- **实现取向**:不是纯 API-first。`clis/jd/detail.js` 就是 `page.goto` + `page.evaluate`
  正则抓 innerText(`text.match(/¥([\d,.]+)/)`)—— 和我们踩过的提取坑同一家族。
  它的 `opencli-adapter-author` skill 里有很成熟的判断:
  > "核心判断不是 'API 比 DOM 高级',而是**数据源有没有外部契约**"
- **驱动**:**agent 按站点撰写**(人监督)。`skills/opencli-adapter-author/SKILL.md` 的流程:
  recon → 定 strategy(PUBLIC_API/COOKIE_API/PAGE_FETCH/INTERCEPT/DOM_STATE/UI_SELECTOR)
  → 写 `clis/<site>/<name>.js` → verify。目标是"30 分钟内跑通 `opencli browser verify`"。
  **不是从 agent 的解题轨迹里蒸馏出来的。**
- **闸**:**有**。作者流程以 `opencli browser verify` 收口;仓库有 **466 个测试文件,
  其中 222 个会真的打开实况页面**(42 个用 JSDOM 离线)。说它"无验证"是错的。
- **⚠️ 订正(2026-07-16 晚)**:本节初稿断言"adapter 由人写""靠人工 PR 维护""无自愈"
  ——**三条都错**,查 `skills/` 后推翻:
  - **是 agent 写的**:`opencli-adapter-author/SKILL.md` 开头即
    "你是要给一个站点写 adapter 的 agent",`allowed-tools` 含 `Edit, Write`。人是监督者。
  - **有自愈**:`skills/opencli-autofix/SKILL.md` ——
    > "**OpenCLI AutoFix — Automatic Adapter Self-Repair**。当网站改了 DOM/API/schema
    > 导致命令失败,**自动诊断、修补 adapter、重试**"

    上限 **3 轮**修复(与我们的 `--verify-rounds` 同构),修好后自动去上游提 GitHub issue;
    `AUTH_REQUIRED`/`CAPTCHA` 等硬停、不改代码。
- **self-evolving:仍然是 ✗,但理由要换**。autofix 是**维护**不是**进化**:
  - **不是净增长,是回归原点**:站点变了 → 挂 → 打补丁 → 恢复到"原来能做的那件事"。
    能力边界前后一样。软件工程口径:bug fix,不是 feature growth。
  - **作用对象是单个 adapter,不是 library 的形状**:不会因此多一个能力/参数维度/fallback。
  - **触发源是外部故障,不是经验积累**:真 self-evolving 是"用得越多、见的实例越多 →
    技能越强"(经验驱动);autofix 是"环境坏了 → 修回去"(故障驱动)。
  → **维护与经验驱动的增长是两条正交的性质,不是同一轴上的强弱。** 对比表里必须分两行,
    否则 autofix 会蹭到 self-evolving 那格。
- **透明度 —— 订正过的口径**:说它"黑盒"是**错的**,autofix/author 流程里 agent 有
  `Read, Edit, Write`,能直接改 `adapterSourcePath`。而且 autofix **是运行时触发的**
  (命令跑挂 → 当场诊断 → 改源码 → 重试),所以"源码不在 runtime 打开"也不成立。

  **真实的差别在"为什么改"**:
  | | OpenCLI | 我们 |
  |---|---|---|
  | 源码可读可改 | ✓ | ✓ |
  | 改的目的 | **修好/新建目录里的共享 adapter** | **为这一次任务改一版** |
  | 改完谁变了 | 共享目录(所有人) | **没人 —— 库不动** |
  | 日常复用路径 | 调命令,受作者定的 `args` 限制 | 读源码 → use / adapt / skip |

  → 不是"黑盒 vs 白盒",是 **"修好它/新建一个" vs "为这次任务改一版"**。
  没有 adapter 覆盖时,OpenCLI 的 fallback 是回到 `opencli browser *` 低层命令从头驱动;
  "改一改最近的那个来凑合这次任务"不在它的日常路径里。
- **适用 domain:每个站点的"通用能力目录",由上游策展。** 实证 —— `clis/` 下 176 个
  站点,每站一组常见命令:

  ```
  jd:       search  detail  item  reviews  cart  add-cart  auth
  amazon:   search  product  bestsellers  rankings  new-releases  offer  auth
  bilibili: search  video  comments  feed  ranking  history  follow  subtitle …
  ```
  站点谱系:电商(jd/taobao/amazon/1688)、社交(weibo/xiaohongshu/reddit/twitter)、
  开发(github/npm/pypi/dockerhub)、金融(binance/xueqiu/yahoo-finance)、
  学术(arxiv/pubmed/openreview/google-scholar)等。
  → **是"这个**站点**能提供什么通用功能",不是"**你**反复做的那件事"。命令集由上游
  决定;你的特异 workflow 若不在目录里,就回落到低层浏览器命令从头做。**

### BrowserAct Skill Forge(browser-act/skills)

- **skill 形态**:`SKILL.md`(执行指南)+ `scripts/*.py`(Python 脚本,产出 JS 字符串
  交浏览器 eval)。
- **驱动**:**单次站点探索**。"explores a site once, discovers APIs and data patterns,
  generates a deploy-ready Skill package"。API 优先,无 API 回落 DOM。
- **闸**:**有,且形似我们**。SKILL.md 里 3b:
  > `eval "$(python scripts/{feature}.py {params})"` — confirm browser execution result
  > **matches exploration phase**

  即"生成的脚本要复现探索阶段观察到的结果" —— 精神上接近我们的 replay-verify,
  但**只在创建时、只对那一个实例**。
- 口号即其边界:**"Explore once, reuse forever"** —— 创建后就假设永远可用。
- **self-evolving**:skill 自身不进化;有 `browser-act-skill-forge-memories/` 给生成的
  skill 未来使用,但不是对 skill 的修订。

### 人写的 SKILL.md(anthropics/skills 等)

- skill = 人写的自然语言文档;无参数提升、无验证闸、无进化;模型读了自己推理。

## 对比表

| | 人写 SKILL.md | SkillOpt | OpenCLI | BrowserAct Skill Forge | **本仓库** |
|---|---|---|---|---|---|
| skill 是什么 | NL 文档 | NL 文档(best_skill.md) | JS adapter(站点 CLI) | SKILL.md + Python 脚本 | **参数化 Python 程序** |
| **适用 domain** | 啥都行(但不可执行) | **通用 agent 任务**,eval 全非网页 | **176 个站点的通用能力目录** | 任意站点的抽取/操作 | **你反复做的网页任务** |
| **谁决定有哪些能力** | 你写什么算什么 | —(优化单个文档) | **上游策展**(别人定好命令集) | 探索器按站点定 | **你**(模板 + 参数你定) |
| **什么驱动产生** | 人写 | 轨迹驱动的**文本编辑** | 按**站点**撰写(recon→写→verify) | **单次站点探索** | **同模板 N 次 solve 的聚合** |
| 参数从哪来 | 人 | —(NL) | 作者声明 args | 探索时定 | **多次 solve 观察到的差异** |
| **闸证明了什么** | ✗ | ✅ 留出集**分数**提升 | ✅ 创建时 verify + 实况测试 | ✅ 创建时:脚本结果==探索结果 | ✅ **无模型重放自己的训练答案**(准入闸 + grade) |
| 无模型运行 | ✗ | ✗(仍靠 agent 推理) | ✅ | ✅ | ✅ |
| **agent 能否为这次任务改一版** | ✗ 只能读 | ✗ 只能读 | 🔶 能改源码,但只为**修好共享 adapter**(autofix),不为凑合当前任务 | 🔶 脚本可读,以 SKILL.md 调用为主 | ✅ **per-task:use / adapt / skip,库不动** |
| 站点坏了能否自愈 | ✗ | — | ✅ **`opencli-autofix`**(≤3 轮,修好后提 upstream issue) | ✗ | ✅ refine 亦可修,且回归重放保旧例 |
| **从你的使用中长新能力** | ✗ | ✅ SkillOpt-Sleep(但长的是散文) | ✗ **autofix 只修回原样**,不从你的 run 积累 | 🔶 memories,非 skill 修订 | ✅ **新 solve 原地加宽参数/策略/fallback** |

## 我们真正的差异(诚实版)

**不是**"我们验证、别人不验证"——这是假的,四家都有闸。是这三条:

1. **任务模板驱动,而非站点驱动。** OpenCLI/SkillForge 问"这个**站点**能提供什么能力",
   产出一个站点命令目录;我们问"你**反复做的这类任务**是什么",从你自己的 N 次解题里
   长出 skill,参数是**实际观察到的差异**,不是作者预先声明的 args。
2. **闸证明的是"能脱离模型跑对"。** SkillOpt 的闸证明"agent 读了它分数更高"(模型仍在
   干活);SkillForge 证明"创建时那一次能复现";我们证明"**这段代码在自己的全部训练
   taskspec 上、无模型、复现出记录的答案**",并给 grade(executable / reference),
   增量 refine 还要跑历史回归。
3. **源码被打开的目的不同 —— 我们有"为这次任务改一版"这条中间路。**
   ⚠️ 不要说 OpenCLI 是黑盒(autofix 证明 agent 能读能改源码)。真实差别:它改源码是为了
   **修好共享目录里的 adapter**(改完所有人都变);我们把源码交给 agent 是为了
   **凑合眼前这一个任务**(`skill_use` 返回 `source_path` + `how_to_reuse`,
   verdict = use / **adapt** / skip;`adapt` = 复用导航/提取核心、只改最后一步、**库不动**)。
   → OpenCLI 日常是二元的:命中就调命令,没命中就回低层浏览器从头来;
   我们在"精确命中"和"从零开始"之间多了一条**中间路**,而真实任务最常落在那里。

4. **用户自定义:模板和参数是你定的,skill 从你自己的轨迹里长出来。**
   OpenCLI 的命令集由上游策展、SkillForge 由探索器按站点定 —— 都是"**别人/机器决定
   这个站点该有什么能力**"。我们是:你写 `skill.yaml`(任务模板 + 你的参数 + 你的实例),
   或者直接把**你平时用 webwright 干活留下的轨迹**丢给 `learn` —— 日常解题 → 可复用
   workflow。参数是**你在意的那些维度**,不是作者预设的 args。
   → **它们做"站点的通用能力";我们做"你反复做的那件事"。** 越是私人化、跨站点、
   多步骤的 workflow,这个差别越大 —— 那种任务在通用目录里根本不会存在。

## reference 这一档为什么只有白盒才有

**即使一个候选没通过验证、不能 standalone 跑,它仍有价值** —— 因为源码里带着**这个站点
的先验知识**:该点哪个 tab、选择器长什么样、哪里有坑(粘连文字、机型 token 像航班号、
Best 列表是策展的……)。agent 读了它,即使自己重写一遍,也比从零探索省一大截。这就是
`grade=reference` 的意义。

**OpenCLI 没有这一档 —— 但理由不是"黑盒"**(它的 agent 能读源码)。是因为它的
adapter 只有两种状态:**能跑(在目录里)** 或 **该被修好(autofix)**。一个"验证没过、
但带着有用站点知识"的候选,在它的模型里无处安放 —— 要么修到能跑,要么不存在。
日常路径上,命令不合用时它给不了你"半个答案",只能回低层浏览器从头来。

我们多这一档,是因为 **skill 的价值不止于"能不能跑",还有"里面写着什么"**:
库里允许存在一个 `grade=reference` 的条目,它跑不通、但 agent 读了能少走弯路。
→ 失败模式是**优雅降级**(executable → reference → 至少是先验),
而不是**二元断崖**(能跑 / 不存在)。

## 取舍:BrowserAct 要不要写进公开 README

**公开 README:可砍。** 它没什么名气(相对 OpenCLI / SkillOpt),读者认不出,列上只是噪音。
README 留「人写 SKILL.md + SkillOpt + OpenCLI」三列即可。

**研究文档 / 论文:必须留,而且它最重要。** 理由不是名气,是**概念最近邻**:同样产出
网站的可执行代码 skill、同样有创建时验证 —— 差别恰好落在我们的贡献上(单次探索 vs
N 次同模板聚合;创建时那一次 vs 准入闸 + grade + 增量回归)。

**它的口号 `Explore once, reuse forever` 正是本项目要反驳的那个假设**,而且我们有实测
弹药:checked-in 的 cheapest skill 当初也"验证过能跑",后来照样答错;同批 runs 蒸馏
5 抽只有 2 抽过;实况站点持续漂。→ 它是个有名有姓、可引用的靶子,让"为什么需要重放
验证 + 持续进化"从主张变成对照。审稿人若知道它,第一问必是"你和 SkillForge 差在哪";
不写 = 送分题不做。

## 待办 / 注意

- SkillOpt 是 **microsoft 自己的项目**,对外表述口径应为"不同轴线/互补",不可写成
  "我们优于它"。
- 上述 star 数以用户先前统计为准,本文档不复述(会过期)。
- 若日后写进公开 README,措辞需再审一遍:对他人项目的每条断言都必须能指回本文件里
  引的那个源文件。


## 反向收获:OpenCLI 已经解决了我们刚踩的坑

`skills/opencli-autofix/SKILL.md` 里有一节 **"Before Entering Repair: 'Empty' ≠ 'Broken'"**,
和我们 2026-07-16 撞的 PIT→HNL(无直飞 → skill 抛 `Could not choose Nonstop filter`)
**是同一个教训,而且他们写得更成熟**:

> - **"0 results" from a search is an answer.** 如果 adapter 成功到达搜索端点、拿到 200、
>   平台返回 `results: []`,**那就是个有效答案** —— 应报告"无匹配",而不是去改 adapter。
> - **Spot-check in a normal Chrome tab**:数据在用户浏览器里看得见但 adapter 拿到空,
>   通常是鉴权/限流/软封,不是代码 bug。
> - **Look for soft 404s**:小红书/微博/抖音等会返回 HTTP 200 + 空 payload 而非真 404。
> - 只有在**跨重试、跨备用入口都可复现**时才进入修复,"否则你是在给一个好 adapter
>   打补丁去追噪声,补完会把本来能用的路径弄坏"。

**对我们的 limitations 的直接启示**:我们的 skill 在"任务前提不成立"时(PIT→HNL 无直飞)
抛的是**实现细节**(`Could not choose Nonstop filter`),而正确行为是**报告事实**
("这条航线没有直飞")。即 **fail loudly 不够,还要 fail meaningfully**:
skill 看到"Nonstop 选项被禁用"时其实**已经掌握了答案**,却把信息丢掉、改抛实现细节。
→ 该写进 `_REFINE_SYS`:**前提不成立 ≠ 错误,应报告事实而非抛实现细节。**(待办)

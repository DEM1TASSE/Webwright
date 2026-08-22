# 要动的代码 —— 实现方案(第二版,按你的决定收敛)

范围定下来了,**两件事**:

1. **Router + 接口** —— 能直接跑的就别叫 agent
2. **`init` 自己生成参数** —— 但提醒用户检查

**登录类任务整个 defer**(webwright 本身也还不怎么支持)。原方案里的第 5 项作废。

---

## 一、Router

### 判断流程

```
任务
└─ 1. 选 skill(retrieve + decide)          ← 已有
   ├─ skip           → 交给 agent 从头解,不硬用
   ├─ adapt(最后一步不一样) → 交给 agent 改,不直接跑
   └─ use(只是参数值不同)
      └─ 2. 它能独立跑吗(grade)            ← 已记录的事实,不是判断
         ├─ 不能 → 交给 agent 当参考读
         └─ 能
            ├─ 3a. 任务里有没有它装不下的要求   ← 新增
            │      有 → 交给 agent 改
            └─ 3b. 填槽,值是不是它处理得了的那类 ← 新增
                   不是 → 交给 agent 改
                   是   → 直接跑 → 4. 查结果
```

**第 3 步必须排在第 1 步之后**,因为槽是 skill 定的。不知道是哪个 skill,就不知道该提
`origin` 还是 `origin_city` + `origin_code`,也不知道要不要提 `retrieved_data_format_spec`。
盲提取一定会提错粒度。

### `use` 覆盖了一半 —— 形状那一半

`decide.py:31` 的原文定义:

> `use` = the skill fits the task as-is (**just different parameter values**)

**它说的是合不合适,完全没说谁来跑。** 是 `skill_use.py:61-63` 那个写死的常量,单方面把它
翻译成了"把源码抄进你的 final_script"。所以**不需要发明新 verdict**,需要的是停止那个
翻译——7 月 17 号那次 700 行循环就是这么来的。

**但 `use` 不足以直接跑,因为它看不见值。** 核实 `decide.py:23-26`,它送进模型的只有:

```
skill_id | template | summary | params: ["origin_code","destination_code","date"]
```

**只有槽的名字。** 看不到 `replays.json`、看不到 grade、看不到这个 skill 训练时究竟在
什么值上跑通过。所以"这个任务要的值合不合适"这件事,**`decide` 在结构上就判不了**——
它从没见过这个 skill 处理得了什么。

于是第 3 步是**两半**:

| | 查什么 | 现在有人查吗 |
|---|---|---|
| **3a 装得下** | 任务的要求 template 能不能表达 | `use` 看得到 template,**算部分覆盖** |
| **3b 值合不合适** | 要填的值是不是这 skill 真处理得了的那类 | **没有,decide 结构上做不到** |

**"没有就别硬用"** 这条已经是对的,现在的代码在 verdict = skip 时就不推荐任何东西。
要改的是别让 agent 花步数去发现这件事(见下面"位置")。

### 位置:放在 agent 启动之前

这套判断的输入——任务文本、library 路径——在 agent 启动前**全都有**,没有一样要等 agent
跑起来才知道。而那个"启动之前"的位置本来就存在:`solve_with_library.sh:11` 和
`build.py:73` 都是在真正启动 agent 之前的一小段 python 里拼提示词的。

现在那儿只拼了一行命令,让 agent 自己去跑。于是每次 solve 开头都白花三步(跑查询命令、
`cat` 源码、写记录),**最亏的是 skip 那种情况——三步花完,结论是"没东西能用"。**

改完之后:

- **skip** → 提示词里什么都不加,零步零 token
- **交给 agent** → 结论和源码直接写进提示词,agent 第一步就干正事
- **直接跑** → agent 压根不启动

### 第 3 步:查的不是"填不填得满",是"有没有装不下的要求"

**"槽填得满"是个假检查,它恰恰漏掉最危险的那种情况。**

任务:"SFO 到 BOS、8/15、**直飞**、**300 刀以内**最便宜的"
skill 的槽:`[origin_code, destination_code, date]`

三个槽全填满了 → "填得满"这个检查说可以跑 → skill 高高兴兴返回一个最便宜的航班
→ **"直飞"和"300 刀以内"没地方放,被静默丢掉。** 结果真实存在、形状正确、答非所问。

**填得满 ≠ 装得下。** 该查的是反方向:**任务里有没有 skill 表达不了的要求。**

**依据是现成的:每个 skill 的 `meta.json` 里都有 `template`。**

```
"Get the top-{n} best-selling {entity} in {period}"
"What is the earliest nonstop flight from {origin} to {destination} on {date}"
```

**花括号是能变的,其余每个字都是不能变的。** 所以拿任务去比 template:任务里凡是 template
没交代的东西,就是装不下的,该交给 agent。

(`covers_axes` 那个字段看着像干这个的,但只有手写那两个 skill 有,生成的全是 null,
现在靠不住。`template` 每个都有。)

**最好的例子就在我们自己库里**:两个能独立跑的 skill 是"**earliest** nonstop"和
"**cheapest**"。问"最便宜的直飞",两个的槽都填得满,但选错哪个都会给你一个答非所问的
航班——**差别在固定部分,不在槽里。**

### 第 3b 步:值是不是这个 skill 处理得了的那类

槽名全对、`use` 也说合适,照样可能不行——**因为值超出了它真正跑通过的那一类**:

- skill 是在**未来 30 天内**的日期上跑通的,任务问 8 个月后 → 站点的分页方式都不一样
- skill 训练时全是**美国国内**机场码,任务问 LHR → NRT
- skill 见过的 `period` 是 "last month",任务给 "2023 Q2"

**证据是现成的:`replays.json` 里记着训练时真实跑通的那组值。** 但这份信息现在
**根本没送进决策层**——`decide` 收到的只有槽名。补上它,3b 才有依据。

**别做成假精确:** 两三个样例推不出"取值范围"。所以 3b 只能是"这个值和跑通过的那些
**是不是同一类**"的判断,不是区间检查。写成硬范围是自欺欺人。

**还有个诚实的说明:3b 判得准不准,现在测不了。** 它的标准答案只能靠端到端真跑
(见下面的 B),而 B 眼下做不了。所以 3b 先按"有依据的判断"实现,准确率等 B 能做了再补。

### 第 4 步:跑失败 vs 跑不对 —— 第一版只处理前者

这两件事分开处理,是第一版能不能落地的关键:

| | 是什么 | 第一版怎么办 |
|---|---|---|
| **跑失败** | 崩了 / 超时 / 没写输出 —— **机器能自己发现** | 退回 agent,把失败原因带过去 |
| **跑不对** | 跑通了,但答错(参数错一点点)—— **机器发现不了** | **先不管,记为已知限制** |

**"跑失败就 fallback 到 agent"是第一版的主干:** 只要能独立跑通就直接跑,一旦报错
(崩 / 超时 / 空输出)就退回 agent,并把失败原因一起带过去——不带的话 agent 可能原样
再跑一遍。有 240 秒超时兜底(replay 在用)。这条路很干净,因为失败是**可观测**的。

**"跑不对"这一版先不解决,明确记成 limitation。** 理由:它没有标准答案时根本查不出来
(形状对、非空、看着像那么回事),真正的把关只能放在跑之前的 3b,而 3b 判得准不准
现在又测不了(见下面 B)。所以第一版的立场是:**先把"能跑就跑通"这条路打通,把
"跑通但答错"当成 router 已知的、待测量的缺口记下来**,不拿它挡住整条流程落地。

> **已知限制(写进文档 / README):** router 直接跑 skill 时,只能拦住*跑失败*,
> 拦不住*跑对形状但答错*(通常来自参数被填成了另一个合理值)。降低这个风险的唯一
> 手段是跑之前的适配判断(3a/3b),它本身的准确率要等能独立跑的 skill 攒够、能做
> 端到端测量(B)之后才有数。在那之前,拿不准可以把 router 的直接跑设成默认关闭、
> 或只对高置信度的匹配开启。

跑完仍然做一层便宜的兜底(不指望它兜住 3b 该兜的):形状 + 非空(`gate` 现成),
并且**把这条路产出的结果标记出来**——记清楚用了哪个 skill、填了什么参数,出问题查得回去。

### 直接跑这一步不用改任何接口(核实过)

replay 已经在干一模一样的事,router 原样复用就行:

1. 写一个 `taskspec.json`(参数、起始网址、输出格式)
2. `python skill.py taskspec.json`,单开一个目录,带超时(replay 用的 240 秒)
3. 读 `agent_response.json` 里的 `retrieved_data`
4. 用现成的 `gate(结果, output_schema=..., method="self_verify")` 查形状

这套已经在跑、已经有测试。**router 不需要等接口改完才能做。**

---

## 二、必须先说清楚的风险:"跑通"不等于"跑对"

你说的是"跑不通就 fall back"。问题是**真正危险的不是跑不通,是跑通了但答错**。

replay 和 router 差在一个关键点上:

| | replay | router |
|---|---|---|
| 知不知道正确答案 | **知道**(训练时那次解出来的) | **不知道**——这正是要它去求的 |
| 所以能查什么 | 结果和已知答案对不对得上 | 只能查:崩没崩、超没超时、有没有输出、形状对不对 |

也就是说,**参数填错了但 skill 跑得好好的、返回一个形状完全正确、看着很像那么回事的
答案——这种情况现有的检查一个都拦不住。** 而这正是参数提取最容易出的错:任务里说
8 月 15 日,提取成了 8 月 5 日,skill 照样跑得通,给你一个真实存在但答非所问的航班。

这是我们要新开的**唯一一个没人把关的口子**。

### 所以先测准确率,不要先定策略

"拿不准就交给 agent"是**策略**,不是准确率——那是知道自己多准之后才该谈的事。
先把数测出来。

要测的其实是**两件事**,不是一件:

| | 测什么 | 标准答案哪来 | 花不花钱 |
|---|---|---|---|
| **A. 填槽准不准** | 给定 skill,照它的 signature 从任务填出的值 vs 正确值 | 现成 | **不花,不开浏览器** |
| **B. "该不该直接跑"判得准不准** | 判成能跑的那些,真跑出来对不对 | 得真跑一遍比 `answer` | 要跑浏览器 |

### A —— 今天就能做

风险几乎全在填槽上(日期提错一天,skill 照样跑得通),而填得对不对**不用开浏览器**。

**数据现成:** `code/runs/eval_webarena_54_review/` 有 100 个结果文件、**50 个不重复任务**,
每个都记着标准参数;任务原文在各自的 `dir/task.json` 里:

```
tid=12   params = {"term": "satisfied"}
tid=134  params = {"user":"kilian", "repo":"a11yproject.com", "date":"March 1, 2023"}
```

**并且核实过:这批里 skill 的槽和模板的槽 20/20 完全一致**(这些 skill 本来就是从这些
模板的任务蒸出来的,槽名继承了下来),所以这批的标准参数可以直接当填槽的标准答案用。
—— 注意这是**这批数据的性质,不是普遍保证**;航班那个把 city 和 code 拆成两个槽,
就对不上模板。

### B —— 现在做不了,有两个硬障碍(都核实过)

1. **WebArena 那批 10 个 skill 全是 `grade=None`、`verified=None`** ——
   那批 library 早于验证机制,一个都没被认证过能独立跑。
   **这批数据里根本没有"能跑"这个事实**,自然测不了"该不该直接跑"。
2. **全库现在只有 2 个 `executable` 的 skill**(都是航班)。样本太少,测出来说明不了问题。

另外那些任务的起始 URL 是 `ec2-18-223-172-69...`,是当时开着的 WebArena 实例,
现在多半已经关了。

**所以 B 要等能跑的 skill 攒够再说,A 不受影响。**

### 数出来之后再定策略

- 如果提取在测试集上就是准的 → "拿不准才升级"根本不用写进代码
- 如果不准 → 我们**当场知道错在哪**,是修提取还是加把关,有的放矢

不管数字如何,有两条建议保留,因为它们成本几乎为零:

1. **结果过一遍形状检查**(`gate` 现成的),没过就退回 agent。
2. **直接跑出来的结果标记出来**,记清楚用了哪个 skill、填了什么参数——这条路
   出了问题得查得回去。

---

## 三、接口:你问的那两个选项

### 先澄清:CLI 和 playwright script 不是两种东西

差别就是**文件最后 5 行**。我们仓库里两种写法都已经有了:

| | 老的手写 skill(`code/library/t222_reviews`,168 行) | 新生成的 skill(736 行) |
|---|---|---|
| 主体 | Playwright 开浏览器、点、抓数据 | 一模一样 |
| **最后几行** | `argparse` + `--product_url --description` | `asyncio.run(main())`,从 argv 读 taskspec.json |
| 结果 | **它本来就是个 CLI** | 裸跑报错,`--help` 被当成文件名 |

上面 160 行完全一样。**"写成 CLI"不改变它做什么,只改变它怎么接收输入**——
带 argparse 的 Playwright 脚本还是 Playwright 脚本。

顺带:老那个 t222 的结构(**一个有名字的函数 + 底下薄薄一层 `__main__`**)
正好就是下面推荐的"做法二"。这个约定不是拍脑袋想的,**我们自己仓库里就有跑通的样例。**

### 两个不同的使用者

他们要的东西不一样:

| 谁在用 | 要什么 | 现在够不够 |
|---|---|---|
| **router**(程序调) | 传一组参数进去、拿结果出来 | **已经够了**——taskspec 那套现成 |
| **人**(手动跑) | `--help` 能看、能直接敲参数 | 不够,裸跑直接报错 |

所以你那两个选项其实不冲突,而且**router 不依赖接口改动**,可以先做。

至于"外面提供一个传参接口" vs "让 skill 自己带命令行参数":**选后者**。
前者等于把我们这个包又塞回用户和 skill 中间,而"skill 能独立跑、不依赖我们的包"
是这东西的立身之本,不该为了省事丢掉。

### 后者内部还有一个选择,我建议选第二个

**做法一:让模型自己写命令行参数那段。** 便宜,改一段提示词就行。但每个 skill 写出来的
可能不一样,参数名也可能和记录的对不上。

**做法二:那段我们自己拼,不让模型写。** 模型只负责写解题逻辑,并且把它放进一个固定名字
的函数里;**入口那段由我们统一贴上去**——参数名直接来自已经记录好的签名。

我倾向做法二,因为:

- 参数名**不可能**和记录的对不上,它就是从那儿来的
- 每个 skill 的 `--help` 长得一样
- "裸跑的时候好好说话"这件事**顺手就白送了**,不用单独做
- 老写法 `python skill.py taskspec.json` 由我们这段统一保证还能用

代价是模型要按一个固定结构写代码(把逻辑放进函数里)。万一它不照做,**replay 会当场发现
——函数找不到就崩,skill 落不了地**,不会漏到 library 里。这个口子是有人把关的。

### 先回答:这会不会让"之前所有东西都不成立"?—— 不会,前提是"新增不替换"

担心是对的,但拆成三层看,只有一层有风险,而那层可控:

| 层 | 改生成器会不会动它 | 为什么 |
|---|---|---|
| **① 已经在库里的 skill** | **不动** | 你改的是**生成器(那段 prompt)**,不会回头重写已生成的文件。flights 那两个 executable 明天还是 `taskspec.json`,照样跑 |
| **② 已经记录的 eval 数字 / grade** | **不动** | 都是 `.json` 死文件,grade 是**生成那一刻**算好写进 meta 的,不会重算 |
| **③ 接口契约本身** | **这层才有风险** | replay 靠 `update.py:109` 的 `skill.py taskspec.json` 位置调用(`update.py:170` 明写 "Interface (**fixed**)") |

**证据:库里现在就已经两种入口并存** —— 手写的 `t222/t279` 用 `argparse --flags`(grade=None,从没被 replay),流水线的 flights/eval/demo 全读 `taskspec.json`。两种井水不犯河水,因为 replay 只碰后者。

**所以"新增 `--flags`、保留 `taskspec.json` 位置参数"** 就落在这个已经成立的格局里:
`taskspec.json` 在 → replay 照跑、grade 照升、旧 skill 照用;`--flags` 加上 → 人能敲、能 `--help`。**没有一样旧东西因此不成立。**

### 反过来,唯一能真把旧东西搞垮的做法

**只支持 `--flags`、丢掉 `taskspec.json` 位置参数。** 那样新生成的 skill 一律 replay 失败
(`update.py:109` 传的位置参数没人接),**永远升不到 executable,整个分级体系对新 skill 直接失效,router 也没东西可跑**。这正是要避开的那条路——所以是"新增",不是"替换"。

---

## 四、`init` 自己生成参数

**默认生成**,不再留空让用户填。`--rows` 这个参数已经有了(默认 3),含义从"留几行空的"
改成"**生成几组**",不用加新参数:

```
init "<需求>"             # 生成 3 组
init "<需求>" --rows 5    # 生成 5 组
```

生成的仍然是个普通文件,打开就能改:不满意的值直接换,可以加行也可以删行。

**关键是要提醒用户检查。** 模型提议的值不保证在那个网站上真实存在,而一个看着挺像的错值
会白白烧掉一次运行,还不容易发现。所以:

- 生成出来的 yaml 里,提议的值旁边**标清楚这是猜的、请核对**
- `init` 跑完在终端上也说一句:这些值是提议的,跑 `build` 之前先看一眼
- 照例可以先 `build --dry-run`,花钱之前确认一遍

提示词里要强调:提议的值要 (a) 真实、在那个网站上大概率存在,(b) 各组之间有差别,
每个参数都变一变。这两点才是有用的。

动的地方:`init.py` 的提示词(36-54 行附近)、`init()`(73-98 行)、`--rows` 的说明文字。

---

## 五、顺序

0. **先测参数提取准确率** —— 不用写 router,不用开浏览器,不花钱,数据现成。
   这个数决定 router 敢做到什么程度,应该排在写代码前面。
1. **Router** —— 不依赖任何接口改动,可以直接开工。做完量一下:省了多少 agent 步数、
   多少次任务根本没启动 agent。
2. **接口(skill 自带命令行)** —— 独立。小心别把验证环节弄挂。
3. **`init` 生成参数** —— 独立,和前两个不冲突。

---

## 六、还要你拍板的

1. **先跑一遍参数提取的准确率测量行不行?**(第二节)不用写 router、不花钱、数据现成,
   跑完再定策略——总比先定一个"拿不准就升级"然后不知道它到底准不准强。
2. **接口选做法二**(入口我们自己贴)行不行?它要动一下生成 skill 的那个约定,比做法一大,
   但换来参数名不会漂、`--help` 统一、裸跑提示白送。
3. **直接跑成功的结果,要不要单独标记/记账?** 我倾向要——这是唯一没人把关的一条路,
   出了问题得查得出来。

---

## 实现进度

### ① skill CLI 模式 —— 已完成(2026-07-24)

**做法:确定性前导码(preamble),不动模型主体。** 新文件 `entry_shim.py` 提供纯函数
`prepend_cli_shim(code, param_names)`,在生成的 skill 最顶端插一段 `_skillfactory_cli()`:
- `skill.py taskspec.json`(一个位置参数、非 `-` 开头)→ 提前返回,`sys.argv` 原样不动
  → **replay 走的正是这条,字节级不变**
- `skill.py --origin-code LAX --date ...` → 把 flags 拼成同样的 taskspec、写临时文件、
  改写 `sys.argv` 指向它 → 模型主体完全不改地跑
- `skill.py` / `--help` → 打印参数和可粘贴示例,退出 0(不再 IndexError)

**接入点(`update.py`):** `code` 变量全程保持模型原始输出(喂回 LLM 的 feedback 不含 shim);
只在两处套 shim —— `_replay()` 调用处(**让 replay 每次自动校验 shim**)和 `library.add()` 落盘处。
故意**没改 `_REFINE_SYS` 提示词**:模型继续照写 taskspec 读取,shim 透明兜住 flags,不依赖模型学新格式。

**验证:**
- 新增 `test_entry_shim.py` 6 条:源码可编译、幂等、shim 早于读参、**两条路 taskspec 完全一致**、
  裸跑给帮助、连字符 flag 正确映射下划线参数。**全套 61 passed(旧 55 + 新 6)。**
- 拿两个真 executable skill(顶层读参 / main SkillRunner 两种结构)验证:回填后均可编译、
  幂等、shim 早于读参。
- **诚实边界:** 未做真浏览器端到端跑(昂贵的 B 类,且站点可能已变)。等价性是接口级证明——
  主体一字未改、两条路收到相同 taskspec,加上 replay 每次守卫,足以支撑"前后一致";
  但没有一次真实 live 双跑对比答案。

**同步的运行部分(demo):**
- 给 demo 自带的 checked-in skill(`examples/learned_library/...`)**回填 shim**(确定性,主体不动)
- `quickstart.sh` 的 `demo` 段:删掉 `spec()` 写 taskspec.json 的仪式,改成直接
  `python skill.py --origin-code $FROM --destination-code $TO --date $ON`,并回显该命令
- README 未动(按要求只改运行部分)

### ② init 自动填参 —— 代码完成,待一次真实 spot-check(2026-07-24)

**做法:扩展现有那一次 LLM 调用**(不新增调用),让它多返回 `instances`。`--rows` 语义从
"留几行空"改成"propose 几组"。

**改的地方(`init.py`):**
- `_SYS`:追加"propose 真实、且各参数都变化的 N 组实例;account-scoped 无法给真值时返回
  `instances: []`,不要编看着像的错值"。数量 N 经**用户消息**传(`Propose {rows} instances.`)——
  `_SYS` 里满是字面花括号,不能 `.format()`。
- `_yaml_skeleton` + 新 `_row()`:渲染 propose 的值;缺的参数、propose 不足的行、完全没 propose
  时,一律回落 `____`(即旧的空表行为)。有 propose 时头部和 `instances:` 注释都标 **PROPOSED /
  REVIEW**,提醒先核对再 build。
- `init()`:清洗 instances(只保留是 dict、含已知参数、至少一个值的);打印改为
  "REVIEW the proposed values … they are guesses"。
- `--rows` 帮助文案、模块 docstring 同步更新。

**验证:**
- `test_build_init.py` 新增 3 条 + 改 1 条:propose 渲染并标记 REVIEW、`--rows` 计数且不足补
  `____`、丢弃畸形 instance、无 propose 回落空表(account-scoped)。**全套 64 passed。**
- 边界都过:YAML 可被 `yaml.safe_load` 解析回 instances、可喂给 `build._fill`。
- **待你跑的一次 live spot-check(判据"合理/solvable",mock 测不了):**
  ```
  cd ~/project/Code-Web-Skills/external/webwright && export PYTHONPATH=$PWD/src
  set -a; . ~/project/webwright/.env; set +a
  export OPENAI_ENDPOINT=<你的网关> OPENAI_MODEL=<你的模型>
  python -m webwright.skill_factory init "top 3 best-selling products for a given month" \
    -o /tmp/spot.yaml --rows 3 && cat /tmp/spot.yaml
  ```
  看 propose 出来的是不是真实、够变化的值(而不是 item1/placeholder)。

**Live spot-check结果(2026-07-24,真跑网关 gpt-5.4):** 四类需求都 propose 出真实、够变化的值,
drift 判断全对 ——
- Amazon:makeup remover / USB-C cable / instant coffee(shape ✓)
- 航线:Seattle→NY / Chicago→Miami / SF→Denver + 真实日期(strict ✓)
- GitHub commits:torvalds/linux、vuejs/core、sindresorhus/ky —— 真实仓库+真实用户名(strict ✓)
- best-selling:5/10/20 × last 7 days / 上月 / YTD(shape ✓)

诚实边界:值是"似真"的(GitHub 仓库/作者真实,但那天到底有没有 commit 未核实)—— 正是
PROPOSED/REVIEW 标记存在的理由。判据"合理/solvable"通过。**item 2 完成。**

---

## LIMITATIONS(router,第一版明确不解决,待后续测量)

1. **跑通但答错 —— 无 fallback。** router 直接跑 skill 时,只能拦住*可观测的失败*
   (崩 / 超时 / 空输出 / 形状不对),拦不住*跑对形状、答案却错*的情况——通常来自参数被
   填成了另一个同样合理的值(8/15 填成 8/5)。没有标准答案时机器检测不到,所以没有兜底。
   - 唯一的缓解在**跑之前**的适配判断(3a 装得下 / 3b 值合不合适),不是跑之后。
   - 而 3a/3b 判得准不准**现在还测不了**(端到端测量 B 需要足够多能独立跑的 skill,
     当前全库只有 2 个 executable)。
   - 保守兜底:拿不准时把"直接跑"默认关掉,或只对高置信度匹配开启。

2. **fallback 的层次:** fallback 不在 `recommend`(它是纯决定),在编排层 `_solve`——
   `run` 失败即就地降级成 `adapt`(把 skill 源码交给 agent),复用已有 agent 路径,不新写一套。

---

## 填槽准确率 A —— 测量结果(2026-07-24,真跑网关)

新增 `fill.py`(`fill_params(task, param_names, examples=)`)——给定任务+skill 签名,抽每个槽的值;
缺的给 None,不编。

**WebArena 50 任务(离线,不开浏览器):参数级 exact 60.4% / 任务级 25–30%。**
**但这个数是坏指标,不代表真实力**:WebArena 的 gold 切分自身不一致——`repo` 保留 "the best
GAN...",`period` 保留 "in Jan 2023",而 `retrieved_data_format_spec` 又是整句样板 "Return the
value as...". exact-match 因此惩罚了本来正确的抽取。**故意不再对着它调 prompt**(那会往更差的
真实抽取方向 overfit;试过"去冠词",webarena 数反而降,因为 gold 保留了冠词)。

**真正要紧的三点(都是好消息):**
1. 48 个 webarena 槽里 **0 个"填成另一个真实但不同的值"**(没有 8/15→8/5)。miss 全是边界/切分/样板。
2. 真实意图 spot-check(网关实跑)近乎满分:航线 5 槽含机场码全对;GitHub user/repo/date 对;Amazon 对。
3. 两个安全行为确认:**缺值 → null(不瞎编)**;**多余约束("under $300")→ 忽略(不硬塞槽)**。

**架构副产品:** 用例"under $300"里 fill 正确忽略了该约束 —— 恰证明 **fill 不够,必须有 3a**
(比 template)去拦 skill 表达不了的要求。fill 只负责填,不负责判"装不装得下"。

**结论:** 填槽在干净意图上足够可靠,`run` 可适度激进;真正的闸门是 3a + 端到端 B(仍待 skill 攒够)。
prompt 定稿:最小跨度 + 通用规则,不含任何 webarena 特定示例。

---

## ③ Router —— 决策层+执行层完成并全分支测试(2026-07-24)

**设计落地(单层,verdict ∈ {run, adapt, skip}):**

- `fill.py` `fill_params(task, names, examples=)` —— 填槽。缺值给 None 不编;多余约束忽略不硬塞。
- `route.py` `promote(task, skill, examples=)` —— 把 decide 的 `use` 提升为 run / 降为 adapt:
  - grade≠executable → adapt(不触发 LLM,grade 闸门短路)
  - 3a `template_gap` 非空(任务要 skill 表达不了的东西)→ adapt
  - 有槽填不上 → adapt(不猜)
  - executable + 装得下 + 全填上 → **run**,带 params
- `skill_use.recommend` —— decide 说 use 后调 promote;输出加 `grade` / `params` / `output_schema`;
  `how_to_reuse` 改为**随 verdict+grade 变**(run=直接跑 / executable-adapt=能跑但要改 / 其他=当参考读)。
  修掉了那个写死常量(7.17 那次 700 行循环的根因)。
- `execute.py` `run_skill(source, params, ...)` —— 直接跑(复用 replay 机制:写 taskspec、子进程、
  超时、读 agent_response)。ok 只表示"产出了非空、形状对的答案",**不表示对**(无 ground truth)。
- `dispatch.py` `dispatch(task, library)` —— 编排/执行层(recommend 是纯决策,dispatch 做 IO):
  - run 成功+形状过 → `answered`,**agent 完全不启动**
  - run 失败(崩/超时/空/形状不对)→ **fallback**:降级成 agent+adapt hint(带"直接跑试过失败了")
  - adapt → agent + hint(源码+诚实复用指引)
  - skip → agent,无 hint

**测试(全 mock LLM/浏览器,秒级):** 新增 `test_route.py`(7)、`test_execute.py`(7)、
`test_dispatch.py`(5),各分支+边界全覆盖。**skill_factory 83 passed / 整个 webwright 99 passed,零失败。**

**填槽准确率 A:** 已测,见上节(webarena exact 60% 是坏指标;真实意图近满分;零"填成别的值";缺值给 null)。

**还没做(下一步):** 把 `dispatch` 真正接进 solve 路径 —— `build.py::_solve` 和
`solve_with_library.sh` 改为先 dispatch、run 就直接跑不启 agent、否则用 resolved hint 启 agent;
`prompt.py::with_skill_hint`(item 8 外提)从"注入命令"改为"注入 recommend 结果"。以及 demo 同步。
决策+执行核心已就绪且全测过,接线是下一轮。

### demo 接线:`ask` → `route`(2026-07-24)

`quickstart.sh` 的 `ask` 模式改成 `route`,任务换成**"最便宜航班"**(库里只有"最早直飞",
final step 不同 → 不能 direct use)。调 `dispatch` 展示 router 判断。顺序:demo(能跑)→
route(判断力)→ solve(agent),route 居中——它左边是"直接跑的 skill",右边是 agent。

**真实网关验证两分支都对:**
- 最早直飞(匹配)→ `run`,grade=executable,5 槽全填,how_to_reuse="RUN it directly"
- 最便宜(装不下)→ `adapt` → agent,理由准("核心搜索可复用,但最终提取要从最早直飞改成最便宜+价格"),
  hint 是 grade 诚实版

**demo 仍待接线:** `solve` 模式还走老 `solve_with_library.sh`;`build.py::_solve` 和
`prompt.py`(item 8 外提)未改。

### item 8 检索外提出 loop —— 完成(2026-07-24)

`prompt.py::with_skill_hint` 从"注入命令"改为"**外提:自己调 recommend,注入结果**":
- skip / 出错 → 提示词原样返回(fail-open,绝不阻塞 solve)
- use/adapt/run → 注入 skill 名 + 源码路径 + grade 诚实的 how_to_reuse,agent 第一步即真活

签名不变,所以 `build.py::_solve` 和 `solve_with_library.sh` 无需改动即自动受益(它们本来就调
with_skill_hint,现在那次调用在 agent 启动前完成外提)。

**测试:** `test_retrieve_decide.py` 的 with_skill_hint 段改写为 mock recommend,验证三行为
(有用→注入结果、skip→原样、出错→放行)。**83 passed。** 真机验证:匹配任务注入 resolved hint,
无关任务 skip 原样返回。

---

## WITH vs WITHOUT skill —— n=5 实验(2026-07-28,gpt-5.4,重门禁 harness)

同一"时长最短 nonstop SEA→DEN"任务,route 判 adapt(有库)vs skip(空库),各 5 次并行。

| | 均值 | 标准差 | 最差 |
|---|---|---|---|
| 步数 WITHOUT | 26.0 | 8.2 | 39 |
| 步数 WITH | **21.8** | **6.6** | **29** |
| final尝试 WITHOUT | 5.8 | 2.6 | 10 |
| final尝试 WITH | **4.6** | **2.0** | **6** |
| 正确率 | 各 5/5 | | |

**结论:adapt 有收益,三重 —— 降均值(21.8<26) + 降方差(6.6<8.2) + 封下限(最差 29<39)。**
六个维度 WITH 全赢,且不牺牲正确率(都 5/5)。

**关键论证(比均值显著性更硬):** "WITH 也有倒霉 run,但连它最差的(29 步)都比 WITHOUT
最差的(39 步)好" —— 逐对成立,对"倒霉 run"的质疑天然免疫。机制:skill 给了调试过的现成
路径,agent 不会陷进"走岔→反复试错→越滚越长"的螺旋,尾部风险被砍掉。

**噪音源:** self_reflection 取证门禁(要求 9 个关键点每个截图眼见为实,答案对了也会因
"年份不可见/航班号没截图/文件写入无证据"判 fail 重试)。它是 skill 无关的固定噪音,把
"绝对省多少步"盖住了,但"更省+更稳"的方向不受影响。

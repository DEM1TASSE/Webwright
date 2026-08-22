# flights 例子的 ground truth 事故:训练答案 2/3 方法就是错的

**日期:** 2026-07-11 ｜ 触发:外部复现发现 checked-in 航班 skill 在 JFK→LAX 返回
$194(真最低 $179)、SEA→JFK 返回 Best 头名 $209。用户假设"训练 ground truth 本身
不对"——查证属实。

## 证据链

1. **训练 3 条航线,2 条方法错**:
   - SEA→JFK(Delta $279):脚本定位了 Cheapest 标签、读了文本、**从未点击**,
     然后取默认 Best 排序第一张卡当"cheapest"
   - SFO→BOS(JetBlue $123):提取正则明写从 "Sorted by **top flights**" 段抓
   - LAX→ORD(American $95):唯一做对的——点击 Cheapest 标签,且答案 == 标签
     aria 宣称的 "Cheapest from 95 US dollars"
2. gate=self_verify(shape)按设计放行了错误答案——文档里"wrong-but-plausible
   answers the agent believed still PASS"的活标本。
3. 蒸馏出的 skill 是缝合体:学到了 lax_ord 的"点 Cheapest 标签",但提取退化成
   body 兜底(整页第一个航司名 + 第一个价格,无位置关联)。训练重放全过,因为
   基准就是这些方法错的答案——垃圾对垃圾互证。
4. **三方一致 ≠ 正确**的具体实例:BASE/WITH/standalone 三条路径共享同一系统性
   偏差(读 Best 头名)时,完美一致且全错。一致性证明的是流程可复现,不是答案对。

## 意外的好消息:oracle 一直就在页面上

Google 的 Cheapest 标签 aria 自带答案:`"Cheapest from 95 US dollars"`。
lax_ord 的 solve 正是靠它锚定才做对的。这就是"给实时数据任务定义 ground truth"
的现成程序化 oracle:

- learn 时可作 gold:`--golds` 由一个无模型探针生成(读标签 aria 的 from $X)
- verify 时可作比较器:答案价格必须 == 标签宣称的最低价

## 处置(按用户指令:不自动修复)

选项待定:A) 用 oracle 当 gold 重新 learn 四条航线(strict,含 JFK→LAX);
B) 手工修 skill;C) 保留现状作为 verify 边界的研究素材。
checked-in skill 目前原样未动。

## 教训(通用)

- 重放验证的保证边界 = "训练分布内、与训练答案一致";训练答案错,验证就在
  巩固错误。gold/oracle 不可替代。
- "N 方一致"在共享偏差下失效;独立性来自**方法不同**的核验(如页面自带的
  声明性 oracle),不是执行路径不同。

## 追问:探针能出 gold,为什么不直接当 skill?

答:对这个家族,几乎就该是——差一个 airline(标签 aria 只有价格,任务要
[airline, price]),所以最优 skill = 导航 + 点 Cheapest + 读标签 aria(价格)
+ 读头卡(airline,价格须与标签一致)。探针是核心,不是全部。

一般化:
- **skill 和 oracle 的距离 = 页面声明性的函数。** 答案被 UI 声明的任务
  (flights),最优 skill 塌缩成"读声明";没有声明的任务(评论、提交数),
  gold 只能外部来,skill 和 oracle 才分开。
- **learn 没学出最简程序的原因:聚合被多数错误带偏。** 训练集 2/3 方法错,
  聚合隐含"多数方法正确"假设;majority 错 → 蒸馏必错。gold gate 的真正作用
  是在入口洗干净 majority。lax_ord 单条见过正确策略,被稀释。
- **选项 A 因此是一次假设检验**:oracle 做 gold 会拒掉两个 Best-top solve,
  只剩方法对的训练材料——若蒸馏收敛到最简声明性程序,证明"给对 gold,
  factory 自己会找到探针";若仍学不出,是蒸馏能力的真短板。两种结果都有价值。

## 2026-07-14 修正:训练答案的"值"当时都是对的,错的是"方法"

复查训练截图(experiments/data/outputs_flights/,自会话临时目录抢救):

- fl_pilot SEA→JFK:截图里 Cheapest 标签明写 "Cheapest from **$279**",Best 头名
  Delta $279 —— 值相等。
- fl_sfo_bos SFO→BOS:标签 "Cheapest from **$123**",Best 头名 JetBlue $123 ——
  值相等。

即三条训练答案在**训练当时全部与页面 oracle 一致**(最便宜航班常常同时是 Best 头名,
巧合概率不低)。所以:

- webwright 的 in-run self_reflection **没有被骗**:CP6("用站点排序识别最便宜")
  判 Satisfied 是有截图证据的——判决引用了标签 aria 的 $279。它验的是"值对",
  验不出"方法脆"。
- 错的层次要改口:不是 "ground truth 错",而是 **方法脆弱、值靠巧合**。2/3 的
  solve 读 Best 头名,恰逢 Best 头名==Cheapest;蒸馏把"读第一个"这个脆方法学了
  进去(还把提取退化成 body 兜底),巧合一消失(用户复现时 JFK→LAX $194 vs $179、
  SEA→JFK $209=Best 头名)就露馅。
- replay-verify 用的是 shape 模式(live 数据无法 strict),所以值从未被钉死。

一句话:**截图级验证能证明"此刻值正确",证明不了"方法在分布外仍正确"。**
方法级的正确性只有两个来源:声明性锚点(点标签、用标签 aria 当比较器)或
多时刻/多路线的 strict 重验。这比原判"训练答案错"更准确,也更有普遍性。

## 2026-07-14 补充:checked-in skill 的精确失败机制(轨迹对、skill 错的原因)

- 来源:3 条训练 run → learn 聚成一个 template 蒸馏;meta `provenance:
  "update-refined", revisions: 1`(又过了一轮 refine)。**meta 里没有
  verified/grade 字段——这个 skill 产生于 replay-verify 功能之前,从未过过闸。**
- 蒸馏不是轨迹复制,是 LLM 重写。导航学对了(含点 Cheapest 标签),甚至
  **oracle 也学到了**:`parse_cheapest_from_tab_label` 会读标签的
  "Cheapest from $X"。
- 错在全新写出的提取+选择逻辑(任何一条轨迹里都不存在):
  1. `extract_result_candidates`:`[role="listitem"]` 在部分页面状态下匹配为空
     → body 兜底,把整页文本里**第一个航司名 + 第一个价格**凑成一对;
  2. `choose_best_answer`:标签价只是 "hint"——先找价格==hint 的候选,找不到
     (body 兜底那对价格对不上)就**降级为"第一个凑齐 airline+price 的候选"**,
     把手里已经拿到的 oracle 价扔了,返回错对。
- 即 JFK→LAX 复现:skill 手里有 hint $179,body 凑出 $194 对,不匹配 → 返回
  $194。**离正确只差一个比较**:若坚持 price==hint(或直接答 hint),就是对的。
- 每条轨迹当时值对,是因为其提取锚定了当时页面的实际呈现;合并版的提取谁也
  不锚,其失败路径(兜底)在训练中从未走过——验证自然也没覆盖。

## 2026-07-14 新事实:价格是客户端相对的

同一分钟同一查询:本机 headless 探针读 $109/$279/$154(LAX→ORD/SEA→JFK/SFO→BOS),
用户自己浏览器看到 $98/$248(前两条,均低 ~11%)。Google Flights 报价随
IP/账号/市场分区变化 ⇒ **"正确答案"是客户端相对的**。

推论:
- strict replay 自洽成立(solve 与重放同客户端);
- 人工在别的浏览器查的 gold 是无效 oracle(验证的是另一个客户端的世界);
- 页面声明性标签是唯一随客户端走的 verifier——skill 运行时读到的
  "Cheapest from $X" 天然就是它那个客户端的真值。声明性锚定 > 外部 gold
  的又一条论据。

## 2026-07-14 机理收紧:Best 是策展列表,最便宜的可能根本不渲染

用户观察证实:不点 Cheapest 时,某些航线/价格在 Best 视图里**完全不显示**
(策展 + "View more flights" 折叠),不是排序靠后,是不在 DOM 里。

- 不点标签的提取在这类航线上原理性无解;Best 头名==最便宜只是条件性巧合。
- 标签价是全库计算的,可见列表是策展的,两者不同步——sfo_bos 被自评打回的
  中间版($189)正是"标签读到 $154 但可见卡片里没有 $154"后掉兜底。
- "方法正确"的完整定义:**点 Cheapest 标签(逼最便宜的卡渲染)→ 用标签价
  核对头卡 → [airline, price]**。只读标签拿不到航司,只搜可见列表两样都可能缺。

# earliest-nonstop 任务家族:跨端 + 独立 oracle 验证跑通

**日期:** 2026-07-16

## 结论
把 quickstart 任务从 "cheapest flight"(价格)换成 "earliest nonstop flight"
(时刻表:[flight_number, airline, departure_time])后,验证故事第一次端到端成立。

## 证据
- 3 条 train solve 从头做,步数 59/40/25(方差巨大 → 正是 skill 钉住流程的价值),
  语义答案全对(仅 SEA→JFK 的 "AS26" 差一个空格,不用 gold 所以无影响)。
- `learn --verify strict` **一次过**,无修复轮:candidate 首次重放就复现三条
  训练答案 → 落库 `what_is_the_earliest_nonstop_flight_from_2c8dab1`
  (verified=true, grade=executable)。
- held-out SEA→DEN:skill 无模型 standalone 跑,答案 == 独立探针
  (earliest_nonstop_probe.py,走不同代码路径)给的值 → **真独立验证,非自证**。

## 为什么这个任务成、cheapest 不成
| | cheapest(价格) | earliest nonstop(时刻表) |
|---|---|---|
| 页面自带真值 | Cheapest 标签,但会漂 | 时刻表按航季稳定 |
| 客户端相关 | 是(IP/账号/会话)| **否** |
| 有歧义 | Best 头名 vs Cheapest | 无 |
| strict 公平 | 只在 learn 紧跟 solve 时 | 隔天重放照样相等 |
| 跨端迁移 | 值不同,做不成 | **值相同,做得成** |

规律沉淀:**当且仅当任务的真值(a)页面声明、(b)客户端无关、(c)无歧义时,
strict 重放 + 独立探针才构成真验证。** 价格三条全违反,时刻表三条全满足。

## 待定 / 已办
- [x] quickstart.sh / 文档 / checked-in example 整体切到 earliest-nonstop
      —— 已提交并 push 到 origin/skill-library(commit 6fc404f + docs 26a8470,2026-07-16)。
- [x] 管线两处改进:_replay 失败带 stderr 尾部、拒收留档 .rejected_*.py
      —— 已提交(commit 90c90c2)。
- [ ] README 两处占位:对比表具名列(skillopt/opencli 等)、Citation 的 author/year。
- [ ] demo 视频仍是旧 cheapest 版;assets/skill_factory_pipeline.png 若含 cheapest 例子需同步。

## 接口决定:自动变体暂不做(2026-07-16)

讨论 `run` 接口易用性时的结论,记档以免遗忘为什么没做:

- 场景:用户只有一个 task,却想要验证过的 skill → 是否系统自动生成兄弟实例来凑 n≥2?
- 难点:**造变体输入免费,造变体的可信答案不免费**。变体只能廉价服务"参数提取"
  (有效且不同即可);"replay 验证"需要每个变体的可信 ground truth,而那要么来自
  page oracle,要么来自用户——factory 不能无中生有。
- 因此自动变体天然只对 **oracle-backed 任务家族** 成立(页面声明答案 + 无模型探针
  裁决),不是通用按钮。
- **决定:initial release 不做自动变体,让用户自己提供实例。** 两条现成路覆盖两场景:
  多解 → `learn`;单任务 → craft。自动变体留 roadmap,想清 oracle 依赖后再开,
  且只对声明性任务开放。
- 一句话原则:**变体输入可自动造,变体真相不能;真相来自页面(oracle)或用户。**

## build/init 实现 + 蒸馏失败根因(2026-07-16)

实现了 init / build / __main__ 三动词(未提交)。验证时 build→learn 连拒两次,查明:

- **根因:`\b` 词边界 vs 粘连文字。** Google 机场选项渲染成 "…AirportLAX…"
  (Airport 与 LAX 之间无词边界)。拒收草稿用 `re.compile(r"\bLAX\b")` 匹配 →
  匹配不到 → 选不中机场 → 崩。能过的草稿(checked-in)用子串包含
  `"LAX" in text.upper()`,粘连照样命中。**同一个坑之前手改 cheapest 时踩过。**
- 即蒸馏失败不是随机噪声,是**具体、可复现的正则陷阱**:模型时不时写出 `\b` 版本。
- **经济判断**:与其盲目多抽(每抽 ≈1 次 LLM ≈ 一条 solve 的 ~1-2%,而 solve 已花
  ~139 次),不如把该坑写进 refine 的 prompt("站点上机场码与名称粘连,禁用 `\b`
  词边界,用子串包含")—— 定向提升单抽成功率,比多抽更省。
- 自动重抽仍值得做(自适应:成功即停、失败封顶 ~3 次退 craft),但 prompt 修正是
  更划算的第一手。待补:5 次独立重抽的实测通过率(进行中)。

### 订正 + 5 抽实测(2026-07-16 晚)

上一节据前两次拒收断言"根因是 `\b` 词边界",**测完要订正**:那是早期两次
build 的原因;跑 5 次独立重抽后,**主导失败模式是 flight_number 提取**。

**实测通过率:2/5 = 40%**(同一批 3 条 runs,gpt-5.4,strict + 3 修复轮)

| Draw | 结果 | 重放 vs 训练 |
|---|---|---|
| 1 | PASS | — |
| 2 | REJECT | `UA 5` / `AS 5` / `B6 5`(三条全抓到孤立的 "5") |
| 3 | PASS | — |
| 4 | REJECT | `UA 030` / `AS 5` |
| 5 | REJECT | `UA 580` / `AS22` |

- **5 抽全部把 airline + departure_time 读对**(United 12:10 AM / Alaska 7:00 AM /
  JetBlue 6:00 AM);**错的永远只有 flight_number**,3/3 失败皆由它造成,
  airport-`\b` 崩溃 0 次。
- 页面对航班号**真值是明确的**(探针实证:该行写着 `UA 729`),但该字段
  **提取极不友好**:与机型粘连(`Airbus A321neo``UA 729`)、旁有酷似航班号的
  token(`A321`)、使用 nbsp(`UA\xa0729`)、训练答案格式自身不统一
  (`AS26` 无空格 vs `UA 729` 有)。
- **区分两个层次**:cheapest 是**任务级**问题(真值漂移/歧义/随客户端);
  flight_number 是**字段级**问题(真值明确但提取困难)。任务选型判据因此
  再加一条:**不只问"答案是否稳定、页面是否声明",还要问"每个字段能否被可靠提取"**。
  `AS26` vs `AS 26` 的空格瑕疵,事后看是该字段的第一次预警,当时被放过了。
- **经济学**:40%/抽 → 自适应重抽期望 ~2.5 抽(12–30 min),封顶 3 抽成功率
  1−0.6³≈78%。**修字段(去掉或锚定 flight_number)预计首抽逼近 100%**,
  故"改任务字段 > 改 prompt > 多抽"。

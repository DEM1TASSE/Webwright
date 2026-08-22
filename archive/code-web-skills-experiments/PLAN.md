# 待办计划(2026-07-07 讨论沉淀)

按优先级排。每条写清:做什么、为什么、大概多大工作量。

## 1. Pipeline diagram(半天)

画"一个任务的旅程 + 库怎么自进化",**不画模块架构图**。核心是把 self-evolving 画成显式的循环:

```
任务持续到来(batch 1, 2, 3, ...)
        ▼
   SOLVE(有库先查 skill_use → use/adapt/skip)◄───────┐
        │ 本批 solve + verdict                          │
        ▼                                               │
   GATE(gold/judge)错解丢弃                           │
        ▼                                               │
   EVOLVE:每个 template 组三选一                       │
     ① 库里没有 → ADD 新技能                            │
     ② 有 + verdict=adapt → REFINE(喂旧代码+新解,     │
        只加宽/修正,保留原函数)                        │
     ③ 有 + 全 use 成功 → 不动                          │
        ▼                                               │
   LIBRARY v₁ → v₂ → v₃ ...(revisions/n_solves 累积)──┘
   下一批用的是长大后的库
```

关键:右侧回边(复用结果是下一次 evolve 的输入)= self-evolving 的图形化。

每个环节标注真实实测数(说服力来源):
- GATE:23/30 过,7 个错解被挡
- ADD:混批 4 template → 4 独立技能,零串码(mixed test B1)
- REFINE:funcs 保留 13/13、11/11、21/22;revisions 1→2→3(mixed test B2/B3)
- 不动:没喂新 trace 的技能一字节不变(mixed test B2 的 t293)
- LIBRARY:长到 10 个技能检索仍 20/20 命中
- SOLVE 回边:held-out 70% vs 55%(+15pp),最狠 33 步→10 步

诚实标注:adapt 路在 WebArena 主实验几乎没触发(49 use / 1 adapt),
REFINE 的数字来自 mixed test,图上注明,别让人以为主实验里 adapt 满天飞。

做两个版本:
- **Mermaid 版**进 `webwright.skills` README + PR #54(GitHub 原生渲染,和文字同步)
- **HTML 精修一页**给 mentor/slides(图 + 主结果表 + t303 案例)

## 2. Demo(回放剧本,1 天)

**回放真实记录,不现场跑**(现跑 10 分钟/题、依赖站点和 gateway,现场必翻车)。
素材全在 `code/runs/eval_webarena_54/runs/` 的 command_history.sh + trajectory 里。

三幕剧本,主角 t303("Philip 在 Jan 2023 提交了几个 commit"):
1. **没有库**:base agent 在 gitlab UI 翻页数,33 步。痛感:探索贵。
2. **库怎么来的**:`python -m webwright.skills.update --manifest ...` 一条命令 +
   技能源码关键 20 行。亮点:3 个 train 解对齐后沉淀的不是点击路径,
   是 `git clone + git log` 这个更好的算法,user/period 已提成参数。
3. **有库**:真实 Step 1(skill_use 命令)→ verdict JSON → 读源码填参数 → 10 步答案对。
   收尾打对比表(70% vs 55%)。

配角 t16(步行+驾车路线):base 两次都错,with 对 → 展示"扭亏为盈"。
一个省步 + 一个扭亏,两类价值都有。

形态:`demo_replay.sh`(逐幕 cat 真实工件,回车翻页)+ 可选录 GIF/asciinema 进 README。

## 3. 人工核对 results(进行中,等标注)

- 已建:`code/runs/eval_webarena_54_review/`(results 拷贝 + REVIEW.md 核对表,
  100 行,带 intent/answer/gold/recorded 列,human_correct/human_steps 留空)
- 待做:人工标注完 → diff recorded vs human → 不一致逐条追根因 → 重新 agg 对账文档数字
- 工具:`code/check_results.py`(三层:重算汇总 / gold 重判 / trajectory 重数步数)

## 4. verdict 行为审计(半天)

问题:verdict(use/adapt)是 agent 自报的(skill_decision.json),动手前写的,
之后实际改了多少没人校验。"use 49 / adapt 1" 严格说是自报意图分布,不是审计过的行为分布。

做法:对每个 with run,把 final_script 和技能源码做函数级 diff(和 mixed test
funcs_kept 同思路)。核心函数保留率高 = 真 use;核心被改写 = 实为 adapt。
全离线,不花 LLM。加进 check_results.py,给文档 verdict 一节加"自报 vs 实测"对照。

## 5. Library v2:按 domain 组织(先做方案 B,2-3 天)

问题(实测):login 在 5 个技能里重复写了 5 遍,open_reviews_grid/fill_route_form 各 ×2。
根因:refine 按 template 独立跑,看不见别的技能,没机会知道"login 已经有人写过"。

- **方案 B(先做)**:生成时去重、物化时内联。库里维护 `domains/<site>/` 的
  primitives 登记;refine 时把同域已有函数签名喂进 prompt("这些已有,直接用别重写");
  产出的 skill.py 仍内联全部代码、保持单文件(agent 侧零改动)。
  验证:拿 shopping_admin 的 4 个技能重跑 refine,看 login 会不会归一。
- **方案 A(验证 B 有效后再考虑)**:真两层(skills import domains),
  tool 返回两个 source_path。干净但改动面大(refine 两阶段 + skill_use 输出变)。

## 6. cost-aware decide(和 paper 主线一起定)

问题(实测):verdict 全 use、从不 skip → 4 例"都对但用库反多花 5-11 步" + 1 例 regression。
根因:decide 只判相关性,没有"从头解贵不贵"的信号。

做法:update 时把 train 的 base 成功率 + 中位步数存进 skill.meta;decide 的 prompt
从 relevance 改成 cost-benefit(能扭亏或省步才 use,base 便宜又稳就 skip)。
先离线 replay 验证(已有 20 个 held-out 的 with/base 对照,不用重跑),再改 runtime。

## 7. Known limitations 一页(写进 experiments 文档)

今天发现的、都有数据的:
- verdict 自报未审计(→ 第 4 条)
- library 按 template 组织,域级 primitive 重复 ×5(→ 第 5 条)
- decide 不会 skip,复用在简单任务上净亏(→ 第 6 条)
- evolve 更新粒度 = 整文件重生成,"增量"靠 prompt 约束 + 事后 funcs_kept 验证,非 AST 级
- 库对 agent 无权限隔离(行为上守规矩:全部 run 只读了推荐的那个技能;架构上没锁)
- adapt 路径几乎未被触发,refine-back 的证据来自 mixed test 不是主实验
- **evolve 蒸馏完不回跑验证技能**(07-07 做 examples 时实测抓到):t303 技能的 "between"
  形式起始月份只认全名,而它自己的 train 参数就是 "Feb"——蒸馏出的技能对着自己的训练实例
  都会崩,但因为从没被执行过,没人发现。roadmap:refine 后用 train 的 taskspec 回跑自测,
  跑不过就把报错喂回去修(等于给 evolve 加个单元测试环节)

## v2 候选(设计好了,刻意不进 MVP)

- **solve 快路径**(07-08 设计):`skills solve -t "task"` 自动 retrieve+decide 选技能 →
  一次 LLM 调用从任务文本填 params → 直接跑 skill.py(不开 agent,秒级)→ 输出自检,
  失败自动回落完整 agent。重复型任务从 10 步 agent 变秒回。砍掉原因:+100 行核心代码,
  是新能力不是包装,值得单独 PR。原型写过一版(solvecmd.py,已删,git 历史可考)。

## 明确不做的(有共识)

- self_verify 升级成 schema validator:它是文档声明的 placeholder,真升级是换 judge/gold,
  不做半套 jsonschema(和 reviewer 达成共识,2026-07-07)
- navigate/mutate 型任务:要 network trace + reset 基建,本轮不做(文档已写)
- 现场跑 demo:回放代替(理由见第 2 条)

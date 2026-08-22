# learn 接口外部用户测试(friendly path)

**日期:** 2026-07-08 ｜ 被测:DEM1TASSE/Webwright @ skill-library(`3612e89`)
**方式:** 外部用户视角,只照 README Quickstart 操作,公网 GitHub 任务,phyagi gateway。
**修复:** 全部 finding 已修,commit `b656e6c`。

## 一句话结论

learn 兑现了"一条命令、免 manifest"的承诺(幂等 ✓、dry-run ✓、产出技能可独立跑 ✓、
复用闭环 ✓:pallets/click → 8.4.2)。但 Quickstart 的"复用"半边对 gateway 用户
**静默失效**——这是本次最大发现。

## Findings 与修复

| # | 严重度 | 问题 | 修复(b656e6c)|
|---|---|---|---|
| F1+F2(合并)| 高 | gateway key 不配 OPENAI_ENDPOINT → skill_use 401 → 被吞成 verdict:skip,**复用整个静默关闭**,与"没匹配到"不可区分。endpoint 配对时 3/3 精确命中——匹配逻辑本身没问题,问题只有一个字:静默 | skip 降级保留(查库失败不弄崩解题),但 JSON 带 error 字段 + "LOOKUP FAILED (library was NOT consulted)" + stderr 吼一行;Quickstart 补 export OPENAI_ENDPOINT/OPENAI_MODEL(注明两步都要)|
| F3 | 中 | gateway 下 learn 甩 ~40 行原始 traceback(401 埋底部)| 归组 LLM 调用失败 → 一行可行动的报错(查 key/endpoint)|
| F4 | 中 | 6/7 run 因缺 agent_response.json 被静默跳过 → 技能从单 solve 蒸馏(n_solves=1),聚合没发生;skip 提示指向不存在的命令 | 跳过计数汇总 + 指向正确的 wrapper/文档 |
| F5 | 低 | 401 时最顶端报 "no running event loop"(webwright 内部,误导)| 未修(不在本模块内),记录 |
| F6 | 低 | wrapper 缺参数时深处崩溃 | 加 usage 校验 |
| F7 | 低 | ANSWER_SPEC 文本泄漏进 template/skill_id | learn 收集时剥离 |

## 定性(测试者的自我修正,重要)

F1 不是 correctness bug——"出错回落 skip"本身是合理降级(复用是可选优化,不该因
LLM 调用失败弄崩 solve)。真正的问题是:一个对 gateway 用户**极易触发**、且
Quickstart **没有提示**的配置错误,表现和"本来就没有可复用技能"完全一样。
修复方向因此是"吼出来 + 文档补位",不是改降级设计。

## 验证通过的性质

- 幂等:重跑 → nothing new to learn,库 md5 不变
- --dry-run:只打印归组计划
- 增量:新实例并入已有 template(refine),不重复建
- 独立执行:skill.py 无模型直跑,答案正确(psf/requests → v2.34.2)
- 复用闭环:skill_decision.json verdict=use,命中正确技能

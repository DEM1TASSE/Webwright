# WebVoyager naive task 拼接 pilot（2026-08-17）

## 目的与设置

本实验只测 long-context / multi-task completion stability，不注入 primitive。选取 6 个已有
GPT-4o 三票全通过单任务基线的 WebVoyager 任务：GitHub--15/14/7 与
Huggingface--3/14/19。将原始 instruction 不改写地编号拼入同一个 prompt、同一个 browser
session；每个子任务要求独立 `SUBTASK <id>` 回答和独立命名的证据截图。

Agent 为 GPT-5.4。每个原始子任务继续按 WebVoyager outcome protocol 独立使用 GPT-4o
三票 majority judge。主指标是 subtask micro accuracy 和 bundle all-pass，避免把部分完成压成
一个无法解释的总分。相对日期题显式向 judge 提供运行日 `2026-08-17 UTC`。

## 结果

| scope | bundle size | bundles | subtask pass | micro accuracy | bundle all-pass |
|---|---:|---:|---:|---:|---:|
| same-site | 2 | 2 | 4/4 | 100% | 2/2 |
| cross-site | 2 | 2 | 4/4 | 100% | 2/2 |
| same-site | 3 | 2 | 6/6 | 100% | 2/2 |
| cross-site | 4 | 1 | 0/4 | 0% | 0/1 |
| cross-site | 6 | 1 | 6/6 | 100% | 1/1 |

总计 20/24 subtask trials（83.3%），7/8 bundles all-pass（87.5%）。但是失败集中在一个
4-task rollout；其余所有 judgeable rollout 合计 20/20 子任务通过。因此结果不支持“拼接越多，
准确率单调下降”，只证明 naive 拼接会引入明显的 run-level completion variance。

## 关键审计

- 4-task rollout 结束时未产出 evaluator 可用的 PNG 证据与正常提交。Agent 已经生成若干
  `.html` evidence，但随后错误切换到系统 Python，判断 `webwright`、Playwright 和浏览器缺失，
  最终返回 environment blocker。按端到端协议整组计 execution failure，不能挑选中间答案复活。
- 6-task 初次 judge 将 GitHub--15 的运行当天时间 `2026-08-17` 错判为未来日期，得到 5/6。
  evaluator 补入 `EVALUATION DATE (UTC): 2026-08-17` 后只复判该子任务，三票通过，最终为 6/6。
- 2-task 四组均为 100%；HF 3-task 为 3/3。GitHub 3-task 最终为 3/3，但经历 80 个 agent
  steps、17 次 final-run，约 28 分钟才通过 completion gate。主要反复点是 GitHub rate limit、
  contributor 拼写和截图未完整覆盖约束。

## Steps（不是浏览器 action 数）

| bundle | steps | final runs | result |
|---|---:|---:|---:|
| same GitHub 2 | 30 | 5 | 2/2 |
| same Hugging Face 2 | 15 | 3 | 2/2 |
| cross-site 2a | 17 | 1 | 2/2 |
| cross-site 2b | 31 | 4 | 2/2 |
| same GitHub 3 | 80 | 17 | 3/3 |
| same Hugging Face 3 | 48 | 5 | 3/3 |
| cross-site 4 | 26 | 1 | execution failure, 0/4 |
| cross-site 6 | 20 | 1 | 6/6 |

这些 steps 是 Webwright agent 的探索/修正轮数，不能直接等同于网页点击数。尤其 6-task run
批量使用 API 完成多个任务，step 数反而较低；因此本 pilot 更可靠的效率信号是 wall-clock、
final-run 重试数和是否完成，而不是单独比较 step 总数。

## 结论与下一步

这次 single-rollout pilot 没有证明稳定的 long-context accuracy degradation。它发现的是：简单
GitHub/HF 任务即使拼到 6 个仍可能全部正确，但运行稳定性有重尾——相同设置下 4-task 可以整组
失败，GitHub 3-task 也可能花费约 28 分钟反复修证据。下一步若要形成可报告结论，应固定 2/4/6
三档、每档至少 3 个 order-balanced bundles，并为每个 bundle 重复 3 个 rollout；同时预注册
20 或 30 分钟 timeout。否则一个 stochastic execution failure 会主导准确率。

结果 artifacts：`/home/t-demiwang/webvoyager-composite-pilot/summary.json`、
`composite.gpt4o.jsonl`、`cross6.github15.date-aware.gpt4o.jsonl`。

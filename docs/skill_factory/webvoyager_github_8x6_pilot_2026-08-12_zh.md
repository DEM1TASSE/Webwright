# WebVoyager GitHub 8-source / 6-held-out primitive pilot（2026-08-12）

本实验严格按 `source scratch → GPT-4o admission → 从零建库并冻结 → held-out scratch/with-lib 配对` 执行。8 个 source 为 GitHub--0/6/8/16/20/23/29/31，全部经 GPT-4o 三次独立判断并以 `[1,1,1]` 通过。由这些轨迹构建的 audited library 含 17 个 primitive；冻结的 `index.json` SHA-256 为 `d0bdde66ee9149d7670e24f039fc119435631046a1b92e28fa073a6e3ee13004`，`package.py` SHA-256 为 `44c995e935ca0f32703dfb375e80b6a032bdebefee4d0e3e7a1818dfe9786bae`。held-out template 与 source template 不重叠，但按预注册映射共享站点能力。

## 结果

| held-out | 共享能力 | scratch | with-lib | primitive selected/used | steps scratch→lib |
|---|---|---:|---:|---|---:|
| GitHub--15 | repository search/overview | 1 | 1 | yes/yes | 14→17 |
| GitHub--14 | repository resolution/contributors | 1 | 1 | yes/yes | 13→14 |
| GitHub--7 | repository/latest commit | 1 | 1 | yes/yes | 14→12 |
| GitHub--26 | GitHub Skills navigation | 1 | 1 | no/no | 13→17 |
| GitHub--3 | pricing acquisition/comparison | 1 | 1 | yes/yes | 16→15 |
| GitHub--37 | Copilot product/docs navigation | 1 | 1 | no/no | 13→11 |

GPT-4o WebVoyager-style judge（最终回答 + 最多 5 张截图、每条 3 votes、majority vote）的所有 12 个结果均为 `[1,1,1]`，所以自动成功率为 scratch `6/6 (100%)`、with-lib `6/6 (100%)`，净分数变化为 0。人工核对成对最终答案没有发现 rescue 或 regression。gate 在 6 个 held-out 中实际选中并执行 4 个，另外 2 个 skip；因此 routing/usage 为 `4/6`。全部任务 steps 合计为 scratch 83、with-lib 86（+3，约 +3.6%）；只看实际使用 primitive 的 4 对任务为 57→58（+1）。这次 pilot 因此证明了跨 template primitive 可以被正确路由并保持正确性，但没有证明成功率或总体执行成本提升；可见的局部效率收益只出现在 GitHub--7（-2 steps）和 GitHub--3（-1 step），被其他任务抵消。

## 审计说明

split 定义在 `evals/webvoyager/github_8x6_split.json`。运行与 judge artifacts 位于 `/home/t-demiwang/webvoyager-github-8x6/`，库位于其 `library/github_com/final_candidate/`。建库最初的 8-workflow 大 batch 因请求过大未完成；改为小 batch 后，Pricing 候选曾因“选择性抽取却宣称完整页面”被 quality gate 拒绝。最终采用单-workflow audited batches 重建，所有 8 批通过质量门后才冻结并启动 held-out，未使用 held-out 做建库、命名或 router 调参。

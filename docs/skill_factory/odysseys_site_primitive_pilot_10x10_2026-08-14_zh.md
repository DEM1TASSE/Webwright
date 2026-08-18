# Odysseys 站点 Primitive 10×10 Pilot（2026-08-14）

## 一句话结论

当前结果不能说明 primitive 在 Odysseys 上整体有效：修复 prompt 污染后，v2 的原始 GPT-4o 输出是 35.9%，但其中一题的伪 PNG 触发了 7 个 API transport error；去掉无效图片并用文本证据重判后，Rubric Avg 为 **40.6%**，仍低于 scratch 的 **48.4%**。目标能力 rubric 从 **7/13 降到 4/13**；agent 探索步数从平均 **56.7 降到 44.3**，但质量没有保住。10 个 held-out 任务中只有 1 个提升、3 个持平、6 个退化。唯一强正例是 MIT apartment/Google Maps 任务，从 0/7 提升到 6/7；因此有局部 transfer 信号，但还没有 aggregate gain。

## 实验设置

- 分支：`odysseys-site-primitives`
- Agent：GPT-5.4
- 官方逐 rubric judge：GPT-4o
- Source：10 个任务（YouTube 5、Google Maps 5）
- Held-out：10 个任务（YouTube 5、Google Maps 5）
- Source 与 held-out template disjoint，但人工要求目标 site capability overlap。
- Source 先执行，再用 GPT-4o rubric judge；只有对应目标 rubric 通过的 site segment 才允许建库。
- 最终严格证据为 7 个 source site segment；另有 2 个 judge 通过的 segment 因无法把保存脚本与被判 final run 精确对齐而排除，1 个目标 segment judge 未通过。
- Held-out 使用同一任务分别跑 scratch 与 primitive arm；primitive 按 site segment 单独 gate。

Split 与结果机器可读文件：

- `evals/odysseys/pilot_10x10_split.json`
- `evals/odysseys/pilot_10x10_heldout_segments.json`
- `evals/odysseys/pilot_10x10_results_20260814.json`

## 建出的库

Google Maps：

- `google_maps/routes/get_driving_directions_summary`

YouTube：

- `youtube_com/search/search_videos`
- `youtube_com/watch/get_watch_page_record`
- `youtube_com/channels/get_channel_about_page_record`

运行时库位于：

`/home/t-demiwang/odysseys-10x10-pilot/site_library_exact`

## 结果

| Arm | Rubric Avg | Perfect | 目标 rubric | Agent steps（总计/均值） | Judge evidence steps |
|---|---:|---:|---:|---:|---:|
| Scratch | 48.4% | 2/10 | 7/13 | 567 / 56.7 | 114 |
| Primitive v1（无效，prompt confound） | 21.9% | 0/10 | 5/13 | 277 / 27.7 | 52 |
| Primitive v2（修复后，原始 judge 输出） | 35.9% | 1/10 | 4/13 | 443 / 44.3 | 102 |
| Primitive v2（修正无效图片 transport error） | 40.6% | 1/10 | 4/13 | 443 / 44.3 | 102 |

v1 不能作为 primitive 效果估计。它把局部 segment 的完整 frozen scratch plan 放在原始整题之前，而且 gate=skip 也注入计划，导致 agent 常把 YouTube/Maps 局部 rubric 当成整题并提前结束。v2 做了两项修复：skip 完全不改变原 prompt；adapt 明确原始整题是唯一完成目标，primitive 只能替换局部 acquisition 步骤。

### v2 逐任务配对

| Task | Site | 全 rubric scratch→primitive | 目标 rubric | Agent steps | Gate | 被评分 final run 实际使用 primitive |
|---|---|---:|---:|---:|---|---|
| `1054858` | YouTube | 4→3 / 7 | 0→0 / 1 | 65→70 | adapt | 否 |
| `0eecee5` | YouTube | 4→4 / 5 | 1→1 / 1 | 88→54 | adapt | 否 |
| `543918a` | YouTube | 6→6 / 6 | 1→1 / 1 | 29→48 | skip | 否 |
| `148dc4d` | YouTube | 6→4 / 6 | 2→1 / 2 | 75→69 | adapt | 是（search、watch） |
| `265abf0` | YouTube | 4→0 / 7 | 2→0 / 3 | 92→20 | adapt | 否 |
| `3add0c2` | Maps | 1→0 / 6 | 0→0 / 1 | 49→16 | skip | 否；两次均无 final run，按 failure 计 0 |
| `4523f5c` | Maps | 5→3 / 7（文本重判） | 1→0 / 1 | 82→19 | skip | 否 |
| `8464610` | Maps | 1→0 / 6 | 0→0 / 1 | 30→22 | skip | 否 |
| `5d157ce` | Maps | 0→0 / 7 | 0→0 / 1 | 41→37 | adapt | 否 |
| `940d8aa` | Maps | 0→6 / 7 | 0→1 / 1 | 16→88 | adapt | 是（driving directions） |

注意：v2 有 6 个 `adapt`，但被评分 final run 只有 2 个真的调用 primitive。router 的 `adapt` 不是 usage；必须结合 `primitive_usage.json` 和 `primitive_execution_trace.jsonl` 报告实际调用。4 个 `skip` 已做到 prompt-neutral，但单次 live-agent rollout 仍有很大随机性：例如 `4523f5c` 在完全不注入 primitive 的情况下从 scratch 5/7 变成文本重判后的 3/7。因此这个 10-pair 单次 pilot 不能把所有差值都归因于 primitive。

## 因果审计：到底是不是 primitive 导致退化

### 先说人话结论

当前机制确实接近“把 primitive 源码复制给 agent，再让它改进最终脚本”，而不是运行时直接调用一个不可修改的 library API。`cross_task_eval.py` 先把通过 gate 的 primitive 源码渲染成一个约 15K–25K 字符的可选 patch，放到原任务前面；GPT-5.4 再自己生成 `final_script.py`。因此有三种不同状态，不能混在一起：

1. `skip`：没有注入 patch，primitive 不可能影响 prompt 或执行；
2. `adapt` 但未使用：agent 看到了源码，但最终计分脚本没有执行它；可能有 prompt/context 干扰，但不能说 primitive 函数运行失败；
3. `adapt` 且实际使用：最终脚本内嵌并调用了 primitive，才能检查 primitive 本身的执行质量。

10 题中，6 题分数下降，但只有 `148dc4d` 这一题在最终计分脚本中真的执行了 primitive。三个退化题是 `skip`，两个退化题虽然 `adapt`，但 `used_primitives=[]`。所以现有证据不支持“primitive 代码导致 6 题退化”；更准确的说法是：**一个实际使用的 YouTube 案例退化、一个实际使用的 Maps 案例大幅提升，其余差值主要来自 prompt 干扰、agent rollout 方差、环境误判和 judge artifact。**

### 是不是原样 copy-paste

不是机械原样复制，但非常接近“copy-paste 后局部改写”。证据如下：

- 注入端：`evals/odysseys/cross_task_eval.py::build_prompt()` 调用 `render_multisite_hint()`，把 `method_code` 作为文本前缀拼到原始任务上；没有 import 一个固定 runtime package。
- 最终脚本：`148dc4d` 的 `final_script.py` 重新声明了 `YoutubeComSearch.search_videos()` 和 `YoutubeComWatch.get_watch_page_record()`，并保留 primitive ID 与源码 SHA；`940d8aa` 同样重新声明了 `GoogleMapsRoutes.get_driving_directions_summary()`。
- agent 会改代码：YouTube library 默认等待 5000ms，最终脚本改成 1500ms；Maps library 默认等待 7000ms，最终脚本改成 1800ms，并加入 trace、fallback 和整题循环。说明它不是调用冻结实现，而是把源码 vendoring 到任务脚本后再适配。
- 这会带来实现漂移风险：例如缩短等待可能降低 live site 稳定性。不过本 pilot 中没有证据证明这两个等待修改直接造成了 `148dc4d` 的丢分；它的 7 次 primitive 调用都记录为 completed。

### Primitive 本身有没有问题

分 primitive 看，答案不是简单的“有”或“没有”。

- `youtube_com/search/search_videos`：在负例 `148dc4d` 中执行 1 次，返回 8 个候选并通过本地 acceptance；没有 crash。它只承诺当前结果页的 title、URL、channel/card text，不承诺“正好选出 6 个合格视频”、hands-on 判断或评分排名。这个 primitive 在自己的窄 contract 内没有显示实现错误，但覆盖范围不足以完成整题。
- `youtube_com/watch/get_watch_page_record`：在 `148dc4d` 中执行 6 次，页面打开和字段采集均 completed；但 playback acceptance 有实质缺陷。函数只返回 `playback_attempted` 和 `playback_control_method`，外层看到 keyboard shortcut 被发送后就记为 `acceptance_passed`，没有验证播放器状态。GPT-4o judge 明确看到 YouTube sign-in/bot gate，判定视频并未成功播放，R6 失败。因此它不是“函数崩了”，而是**验收条件把尝试成功误当成结果成功**。
- `google_maps/routes/get_driving_directions_summary`：在正例 `940d8aa` 中执行 30 次，其中 20 次解析出 2–16 分钟等可见 driving time 并通过，10 次因为 origin 只是 listing 标题而不是可靠地址，返回 `result_unclear` 并走 fallback。它没有把失败伪装成成功，最终 Maps 目标 rubric 从 0→1，整题从 0/7→6/7。这是 primitive 能正确工作并带来收益的直接证据；同时也说明上游必须先提供规范地址。
- `youtube_com/channels/get_channel_about_page_record`：本轮被 route 检索过，但没有进入任何被评分 final run，因而这次 pilot 无法评价其线上效果。

### 逐题证据与归因

| Task | 结果 | 是否注入/执行 | 直接证据与例子 | 当前归因 |
|---|---:|---|---|---|
| `1054858` | 4→3/7 | adapt；未执行 | `used_primitives=[]`；唯一丢分是与 YouTube 无关的 Google Docs 排障 R3：scratch 找到了具体修复建议，primitive arm 打开的是 2019 outage 页面，没有 actionable fix。注入 prompt 比原任务多 19,536 字符。 | 不是 primitive 函数执行失败；可能是长 patch 改变规划/注意力，也可能是 live rollout 方差。 |
| `0eecee5` | 4→4/5 | adapt；未执行 | `used_primitives=[]`；两边 R1–R4 都通过、R5 播放都失败。primitive arm 少 34 agent steps，但没有实际调用，因此不能把省步归功于 primitive。 | 持平；没有 primitive 执行效果证据。 |
| `543918a` | 6→6/6 | skip；未注入 | scratch 与 primitive `task.json.task` 长度均为 606，SHA256 前 12 位均为 `edb46b9e4809`；两边全通过。 | 纯 prompt-neutral control，说明 skip 实现正确。 |
| `148dc4d` | 6→4/6 | adapt；实际执行 search/watch | trace 为 7 entered、7 completed、7 local acceptance：搜索返回 8 条，watch 打开 5 个候选并对最佳视频尝试播放。R3 丢在下游商品验证：Roborock Qrevo Curv 的 Target 页没有成功核验；R6 丢在 playback 被 sign-in/bot gate 拦截。 | 混合：R6 暴露 watch primitive acceptance 过弱；R3 属于 primitive 不负责的 scratch 下游失败。不能说 2 分都由 primitive 代码 bug 造成。 |
| `265abf0` | 4→0/7 | adapt；未执行 | `used_primitives=[]`，final `run_001` 只有 20 steps 且未 reflection。agent 错误断言系统缺少 browser/WebWright，并因调用 `python` 而非环境中的正确入口提前停止；没有收集 10 个视频，也没建 CryptPad。注入 prompt 多 25,119 字符。 | 直接失败原因是 agent 的环境自诊断和提前退出，不是 primitive 调用；长源码提示是否诱发该路径只能算待验证假设。 |
| `3add0c2` | 1→0/6 | skip；未注入 | 两边原任务 SHA256 前 12 位均为 `62439a8e314b`。primitive arm 没有 final run；debug 明确显示 agent错误判断缺少 Playwright/WebWright 后停止。 | primitive 不可能是直接原因；这是同 prompt 下的 rollout/环境自诊断失败。 |
| `4523f5c` | 5→3/7 | skip；未注入 | 两边原任务 SHA256 前 12 位均为 `d35f5654255c`。最初 0/7 是 4 个扩展名为 `.png`、内容却是 UTF-8 文本的 artifact 导致 GPT-4o invalid-image；文本重判恢复 R1、R2、R6。R4/R7 仍失败，因为没有真实截图证明地图/到达情况和最终打开 tabs。 | 原始 0 分主要是 judge transport bug；修正后的 3 分下降是有效视觉证据不足和 rollout 差异，不是 primitive。 |
| `8464610` | 1→0/6 | skip；未注入 | 两边原任务 SHA256 前 12 位均为 `d30ebb975675`。scratch 唯一通过 R4，列出了各城市韩国特色食物；第二次 rollout 遇到 Google CAPTCHA/Yelp denial，没收集 food facts，R4 变 0。 | 明确的 live-site/rollout 方差例子；primitive 没有进入 prompt。 |
| `5d157ce` | 0→0/7 | adapt；未执行 | `used_primitives=[]`；route 认为 Maps driving lookup 可局部复用，但最终脚本没有保留调用。两边目标 commute rubric 都是 0。 | gate→execution 断层；不能评价 primitive 好坏，也没有收益。 |
| `940d8aa` | 0→6/7 | adapt；实际执行 Maps primitive | trace 显示 30 次 commute lookup：20 次 acceptance passed、10 次 `result_unclear` 后 fallback。可见成功例包括 4、9、10、16 分钟。Judge 判定 20 个 listing 的 Maps commute R4 通过，且 R2–R7 全部从 0→1。 | 强正例。primitive 是整题提升的重要组成部分；同时 agent 也做了 listing discovery、筛选、CryptPad 和 tab 管理等大量 scratch 工作。 |

### 为什么总分仍然会变差

1. **比较的不是“同一次执行开/关函数”。** scratch 和 primitive 是两个独立 live rollout，网页状态、反爬、agent 决策都会变。三个 `skip` 退化就是直接证据：它们连 prompt 都完全相同，却仍从 1→0、5→3、1→0。
2. **adapt 会塞入很长的源码 context。** 六个 adapt 任务额外增加约 15K–25K 字符；即使 agent 最终没有调用，规划也已经接受了不同 context。`1054858` 丢的是无关 Google Docs rubric，说明当前注入粒度可能分散注意力。
3. **agent 看见 primitive 不等于会用。** 6 个 adapt 只有 2 个计分 final run 有 usage trace；`265abf0` 和 `5d157ce` 是最明显例子。现有 adapter 缺少“adapt 后必须调用或给出可审计拒绝原因”的执行约束。
4. **primitive 只覆盖局部 acquisition。** `148dc4d` 的库能搜视频、开 watch page，但不能完成 hands-on 判断、9 个产品的官网/零售商双重核验、最终 shortlist 和 tab end-state。局部步骤成功并不能保证长链后半段不掉分。
5. **YouTube playback 的 success definition 不够严格。** “发送了按键”被记录为 acceptance passed，但 rubric 要求“真的开始播放”。这是当前最明确的 primitive contract/验收问题。
6. **artifact 和环境错误会压过 primitive 信号。** `4523f5c` 的伪 PNG、`3add0c2`/`265abf0` 的错误环境诊断，都能让一整题掉到 0，与 primitive 算法质量无关。

因此本 pilot 最稳妥的结论是：**不能宣称 primitive 整体有效，也不能宣称 primitive 本身导致总体退化。** 已经确认一个 Maps 正迁移、一个 YouTube playback 验收缺陷，以及明显的 prompt 注入和执行采用率问题。下一轮应该冻结 primitive 为真正 import/call 的 runtime API、禁止 agent 改写实现，并以同任务多 seed 比较；否则 copy/adapt 漂移和 live rollout 方差会一直混在结果里。

## 为什么目前仍退化

1. **Library 太窄。** 7 个严格 source segment 只生成 4 个 primitive，而 Odysseys held-out 是跨站长链任务；大多数关键工作仍是 scratch。
2. **Gate 到 execution 有断层。** 6 个 adapt 只有 2 个最终实际使用，说明 agent 在合成/修最终脚本时经常丢弃已批准 patch。
3. **局部 primitive 不保证整题收益。** MIT Maps 是强正例，但 robot-vacuum 的 YouTube primitive 满足局部 acquisition 后，整题仍从 6/6 降到 4/6。
4. **Live rollout 方差高。** prompt-neutral skip 也出现大幅差异，单 seed、10 对任务不足以做稳定因果判断。
5. **执行环境自诊断不稳。** `3add0c2` 两次错误判断缺少 Playwright/自反思工具，未生成 final run；本报告保守按 0 分，不删除任务。
6. **Judge artifact 也需要验证。** `4523f5c` 的 4 个 `.png` 实际是 UTF-8 文本，导致 GPT-4o 将 7 个 rubric 全部报 invalid-image error。文本重判恢复 3 分，但目标 R4 仍因没有有效视觉证据失败。Exporter 已增加图片 magic-byte 校验，后续不会再上传这类伪图片。

## 已修的基础设施问题

- Builder 只接纳 GPT-4o 目标 rubric 通过、且能与精确被判 final run 对齐的 site code。
- Candidate ID 从完整 workflow/rubric identity 机械规范化，避免 LLM 丢失 segment 后缀。
- Source adapter 支持显式 `--final-run`，拒绝“较新的未判 retry script”覆盖被判证据。
- Judge exporter 新增 `--mode scratch|primitive`，防止共享 runs 目录时把两个 arm 导出成同一轨迹。
- v2 skip prompt-neutral；adapt 明确局部 patch 不能替代完整 Odysseys 任务。

## 建议下一步

不要立即扩大到更多任务。先做一个更小但可解释的复现实验：固定 3 个强 capability-overlap held-out（包含 MIT Maps 正例、robot-vacuum YouTube 负例、一个 prompt-neutral skip control），每个 arm 跑至少 3 个 rollout；同时把 `adapt` 后“必须实际调用或记录明确 rejection reason”做成 runner 级约束。只有实际使用率、目标 rubric 和整题 Rubric Avg 都稳定后，再扩到 20×20。

运行时原始结果：

- Scratch judge：`/home/t-demiwang/odysseys-10x10-pilot/heldout_eval_scratch.json`
- Primitive v1 judge：`/home/t-demiwang/odysseys-10x10-pilot/heldout_eval_primitive.json`
- Primitive v2 judge：`/home/t-demiwang/odysseys-10x10-pilot/heldout_v2_eval_primitive.json`
- v2 paired summary：`/home/t-demiwang/odysseys-10x10-pilot/heldout_v2_paired_summary.json`

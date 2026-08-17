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

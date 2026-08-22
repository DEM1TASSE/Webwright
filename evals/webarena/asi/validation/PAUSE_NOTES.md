# ASI 臂 — 暂停状态（2026-08-21 20:57）

## 为什么停

`cross_task_eval.py` 在我的臂运行期间被并发修改（mtime 20:51:16，臂 20:48 起跑）。

**修改本身已完成，不需要补 patch**（这是对 20:55 那版本文件的更正）：
`OFFICIAL_FINAL_STATE_SPEC` 取代了 official 任务的 `OFFICIAL_RETRIEVE_SPEC`，
`has_complete_official_artifact` 已接进 :1515/:1543，只校验 `final_state`，
不再要求 `agent_response.json`。定版之后启动的 run 零崩溃。

15 次 process_error 全部落在编辑窗口内（20:47:10–20:51:16），是过渡态的产物。

## 真正的问题：两版 prompt 混在同一条 lane 里

| 变体 | 题数 | 说明 |
|---|--:|---|
| OLD `OFFICIAL_RETRIEVE_SPEC`（要求 agent_response.json） | 119 | 20:47 之前 |
| NEW `OFFICIAL_FINAL_STATE_SPEC` | 32 | 20:47 之后 |
| `NAVIGATE_SPEC` | 42 | navigate 分支，本次改动未触及 |

retrieve 的 151 题分裂在两套输出契约下，**臂内部不自洽**，续跑只会让分裂扩大。

## 结论：只读 lane 需要整条重跑

已完成的 146 题结果作废（`asi/results/` 需清空后重跑，否则 resume 会保留旧 spec 的结果）。
写 lane（188 题 mutate）一题未跑，不受影响。
实例 4 未被写入（只读 lane 无污染），指纹仍是 reset 后的 `"drift": {}`，不必重新 reset。

## 恢复步骤

```bash
# 1. 确认 cross_task_eval.py 不再变动
ls -l --time-style=+%H:%M:%S <repo>/evals/webarena/cross_task_eval.py

# 2. 重新冻结 prompt（现有 PROMPT_FREEZE.json 对应 20:38 那版文件，已失效）
#    冻结脚本流程见 PROMPT_FREEZE.json 的 hashes / rendered_examples 字段

# 3. 清掉旧 spec 的结果，重跑只读 lane
rm -rf /data/demiwang/results/webarena/ww_asi/asi/results /data/demiwang/results/webarena/ww_asi/asi/runs
bash /data/demiwang/results/webarena/ww_asi/run_arm.sh asi

# 4. 配对对照臂
bash /data/demiwang/results/webarena/ww_asi/reset_inst4.sh
bash /data/demiwang/results/webarena/ww_asi/run_arm.sh scratch

# 5. 分析
python3 /data/demiwang/results/webarena/ww_asi/analyze_arm.py \
    --results-root .../asi/results --runs-root .../asi/runs --arm asi
```

## 到目前为止的主结果（146 题，仅 retrieve+navigate，无 mutate）

库引用 **0**、bid 抄写 **0**、`get_by_test_id` 尝试 **0**。
这三个数跨两版 spec 都成立，不受上面那个分裂影响。
通过率不解读 —— scratch 对照臂未跑，且 mutate 那 188 题（ASI 原论文差异最大的一档）未覆盖。

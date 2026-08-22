# 逐任务判分

每个文件是一道题，文件名 `task<官方 task_id>.json`，按站点分子目录。

```json
{
  "run": {
    "run_dir":     "…/official_webarena_task389_20260820_042134",   // 对应的轨迹目录
    "timed_out":   false,
    "return_code": -15,          // -15 = 产物齐了之后被 harness 主动收尾，正常
    "final_state_ready": true
  },
  "evaluation": {
    "score":  1.0,               // 1.0 通过 / 0.0 未通过 / null 未评分
    "status": "scored_correct",  // scored_correct | scored_incorrect
                                 // invalid_final_state = 产物不合规，是基础设施问题不是能力问题
    "eval_types": ["program_html"],   // 官方 evaluator 类型
    "final_url":  "…",
    "judge_model": "gpt-4o"      // 仅 fuzzy_match / ua_match 用得到
  },
  "deployment": { "config": "…", "sites": {…} }
}
```

四个目录的区别：

| | |
|---|---|
| `scores_438_readonly` | 只读题。254 通过 |
| `scores_374_write` | 写题，**主表用这个**。199 通过 |
| `scores_374_write_REPLAY` | 同一批写题，但分数来自 reset 后重放冻结脚本（干净态、恰好执行一次）。169 通过。测的是"脚本能否独立重现"，不是"agent 能否解题" |
| `scores_374_write_REPLAY_VOIDED` | **分数不可用**。第一次重放时 evaluator 漏传登录态，`program_html` 实地导航全部落在登录页。留着只为和上一个比**执行状态**：仅此次失败=并发争抢(11)，两次都失败=脚本真脆弱(42) |

统计脚本在上一层的 `make_results.py` / `box_tables.py`。

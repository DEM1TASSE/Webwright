# 812 全量跑批（2026-08-20）的记录

产出这批结果的机器已不可用，这里是随代码一起保存的记录。结果数据本身另行导出。

| 文件 | 内容 |
|---|---|
| `PHASE_ANALYSIS.md` | 五个阶段的流程与时长、基础设施体检、累加写归因、四种计分口径 |
| `DIVERGENCES.md` | 与官方 WebArena / webwright 原生的全部偏离，逐条带理由 |
| `HOST_CASE_FINDING.md` | Magento 302 死循环的定位过程 |
| `drive_replay.sh` | Phase 1b→4 的驱动脚本：补跑超时 → reset → 三道门 → 重放 |
| `drive_replay2.sh` | Phase 4b：修掉 auth 缺陷后的低并发全量重放 |
| `RESULTS.md` | 分域表（Multi-site 独立成类）、四种计分口径、micro/macro |
| `results/` | **逐任务判分**，1560 个 JSON，四个子目录见下 |
| `results_legacy438/` | 旧版 438 题的判分（对照用，55.7%） |
| `gate_duplication_evidence.json` `gate_multiapply.txt` | 门禁重跑在站点上留下的重复对象证据，reset 前采集，**不可再生** |
| `mutate_write_drift.json` `pristine_fingerprint.json` | 写入增量与纯净态基线指纹 |

## `results/` 的四个子目录

| | |
|---|---|
| `scores_438_readonly/` | 只读题 → 254 = 58.0% |
| `scores_374_write/` | 写题 → 199 = 53.2%。**主表用这个** |
| `scores_374_write_REPLAY/` | 同批写题，reset 后重放冻结脚本的判分 → 169。测的是"脚本能否独立重现"，不是"agent 能否解题" |
| `scores_374_write_REPLAY_VOIDED/` | **分数不可用**——第一次重放时 evaluator 漏传登录态，`program_html` 的实地导航全部落在登录页。留着只为和上一个比**执行状态**：仅此次失败 = 并发争抢（11），两次都失败 = 脚本真脆弱（42） |

每个 JSON 的 `run.run_dir` 指向轨迹目录。**轨迹不在仓库里**（9.1G，含截图），
随结果数据另行导出；这里只有判分，足以复核 `RESULTS.md` 与 `PHASE_ANALYSIS.md` 的每一个数字。

两个 drive 脚本里的路径是那台机器的，不能直接跑；它们记录的是**阶段顺序和每道门的位置**，
可执行的版本见 `../lanes.md` §6。

## 主要数字

| | inline | 累加写修正 |
|---|--:|--:|
| 非 mutate 438 | 254 = 58.0% | — |
| mutate 374 | 199 = 53.2% | 203 = 54.3% |
| **全 812** | **453 = 55.8%** | 457 = 56.3% |

分域、micro/macro、四种口径的完整表在结果目录的 `RESULTS.md`。

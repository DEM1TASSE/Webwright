# ASI 库 × Webwright agent — 跨 harness 迁移臂（2026-08-21）

把 Agent Skill Induction 诱导出的技能库注入 Webwright 的 agent，在官方 WebArena
cross-template 留出集（399 题）上评测。与 primitive / scratch 两个臂**同 harness、同 split、
同实例**，只多一个注入块。

**这是运行中的快照。** 只读 lane（211 题 retrieve+navigate）已完成；写 lane（188 题 mutate）
2026-08-21 22:56 启动，本导出**不含写 lane 结果**。mutate 恰是 ASI 原论文里差异最大的一档。

---

## 结论（只读 lane 211 题）

| | |
|---|--:|
| 判分成功 | 209 / 211（超时 0） |
| 通过率 | 125 / 211 = **59.2%** |
| **库被引用的题数** | **0** |
| bid 序列被照抄的题数 | 0 |
| `get_by_test_id` 尝试 | 0 |

28 个诱导函数注入了 211 道题的 prompt，**一次都没有被引用**。

这与 ASI 在自己 harness 里的结果同向但更彻底：那边 28 个函数有 5 个被调用、覆盖 7% 任务，
全部是 map；搬到 Webwright 后归零。诚实的框架是「这个库没有可迁移的东西」，
而不是「跨 harness 迁移失败」——它在 ASI 自己的 harness 里就已经基本不被使用。

原因在库的形状，不在 harness：28 个函数里 19 个的参数全是 AXTree bid，
即每次渲染重新分配的元素下标。只有第一个 bid 能从当前页读到，其余要等它本该省下的那次导航
发生之后才存在。**必须先做完任务才能凑齐参数。**

`analysis/vs_full812_scratch.txt` 里有一份与旧 scratch 基线的对比（+1.0%）。
**不要引用它**：库引用为 0，任何 delta 都不可能是库效应；而且那个基线跑在不同实例、
不同 prompt spec、不同 harness 上。splits/README §5 测得同系统重跑的任务级翻转率 21%，
399 题配对检验的 MDE 是 6.5%——±1.0% 在噪声里。可引用的数字要等配对的 scratch 臂。

---

## 目录

```
PROMPT_FREEZE.json        冻结的 prompt：hint 模板、逐字保留项、偏离清单、
                          harness/spec/库的 sha256、10 个站点组合各一份渲染样例
prompt_freeze/            那 10 份完整 prompt 原文
library/                  实际注入的 10 个块（按站点组合）+ MANIFEST.json
code/                     本臂的全部脚本，见下
results/                  逐题结果 json（211 题）
analysis/summary_by_site.txt      按站点的通过率 / 超时 / 库引用 / 中位步数
analysis/vs_full812_scratch.txt   与旧 scratch 基线的临时对比（附不可引用的理由）
analysis/analysis_asi.json        逐题：correct / steps / 引用到的函数名 / bid 抄写
logs/                     asi_arm.log、asi.parallel.log、reset_inst4.log
splits/                   cross-template 划分 + 并行/串行 lane + reuse_split
trajectories-readlane-raw.tgz     只读 lane 全部轨迹（1.8G）
discarded_mixed_spec/     被作废那一轮的结果与日志，见下
```

## code/

| 文件 | 作用 |
|---|---|
| `asi_hint.py` | 注入模块。ASI 无检索，所以它不做选择，只贴 `describe()` 的冻结输出 |
| `freeze_prompt.py` | 冻结 prompt 并 pin 哈希；harness 变了就重跑它并 diff |
| `guard_harness.py` | 跑批期间每 20 秒比对哈希，漂移即报 |
| `run_arm.sh` | 两条 lane 的驱动 |
| `make_auth_inst4.py` | 串行重生成 storage_state |
| `reset_inst4.sh` | 按 lanes.md §6 重置实例 4（去掉 auth 那步） |
| `analyze_arm.py` | 按函数名检测复用并出表 |
| `serial_groups_test399.json` | 399 题上的 61 条写作用域链 |
| `deployment_inst4.json` | 实例 4 的部署配置 |

## 复现

```bash
bash code/reset_inst4.sh
python3 code/make_auth_inst4.py
python3 code/freeze_prompt.py          # 必做：确认 harness 未漂移
bash code/run_arm.sh asi
bash code/reset_inst4.sh
bash code/run_arm.sh scratch           # 配对对照臂
python3 code/analyze_arm.py --results-root <root>/asi/results \
                            --runs-root <root>/asi/runs --arm asi
```

## discarded_mixed_spec/

21:29 那一轮作废，因为 `cross_task_eval.py` 在跑批期间被并发修改：
`OFFICIAL_FINAL_STATE_SPEC` 中途取代了 `OFFICIAL_RETRIEVE_SPEC`，导致 151 道已完成的
retrieve 题分裂在两套输出契约下（119 旧 / 32 新），另有 15 题在过渡窗口内崩溃。
只保留结果与日志，不留 2G 轨迹。这正是 `freeze_prompt.py` 和 `guard_harness.py` 的由来——
分裂是事后靠哈希才发现的。

## 代码位置

GitHub `DEM1TASSE/Webwright`，分支 **`webwright-asi-skill-0821`**。
ASI 侧（诱导过程与原始库）在 `DEM1TASSE/agent-skill-induction`，分支 `asi-webarena-eval-0821`。

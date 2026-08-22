# 出处：代码在哪、哪个分支、哪个 commit

机器 GCRSANDBOX410 即将下线。以下 commit 是这份结果对应的**唯一权威代码状态**。

## Webwright（agent + 本臂全部代码与结果）

| | |
|---|---|
| 仓库 | https://github.com/DEM1TASSE/Webwright |
| 分支 | `webwright-asi-skill-0821` |
| 代码 commit | `7b740e506b69ac09b1d8bacc9bc5490017ff7dda` — Add the ASI-library arm to the official WebArena reuse eval |
| 结果 commit | `5465e64bc7505a65bcb12ea227d86d9ef2b2ddbf` — Record the ASI-arm run: findings, per-task results, frozen prompts, logs |
| 父提交 | `8a78474` align reuse eval with official WebArena auth protocol（他人提交，本臂基于它） |

分支内 `evals/webarena/asi/` 下是本臂的全部内容；`asi_hint.py`、`cross_task_eval.py`
的 asi 接入、`run_reuse_eval.py` 在 `evals/webarena/` 下。

## ASI（诱导过程与原始库）

| | |
|---|---|
| 仓库 | https://github.com/DEM1TASSE/agent-skill-induction |
| 分支 | `asi-webarena-eval-0821` |
| commit | `eff0ad13a09d1c00f5c2fb0cc642353e5bae2d0f` |

诱导库的来源 commit 也记在 `library/MANIFEST.json` 的 `asi_commit` 字段。

## 不在 git 里的

`trajectories-all-raw.tgz` —— 226 道题的完整轨迹（截图、每步命令、trajectory.json），
体积过大无法入库，**只存在于本导出目录**。要保留必须单独搬走。

## 环境（不随代码走）

WebArena 实例 4 @ GCRSANDBOX410，部署配置在 `code/deployment_inst4.json`。
站点数据只在那台机器的容器里，随机器下线消失。
重建流程见 `/data/webarena/README.md`（同样在那台机器上）。

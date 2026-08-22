# Web Skill Factory 导出与版本指引

这份文件是 Web Skill Factory 的公开入口。实验分支较多时，不要根据版本号大小猜测
应该运行哪一版；按下面的标签使用。

## 推荐入口

| 用途 | Git ref | 定位 |
|---|---|---|
| 复现正式 Primitive 结果 | [`web-skill-factory-best`](https://github.com/DEM1TASSE/Webwright/tree/web-skill-factory-best) | 唯一 `BEST`，冻结于 `100a0e3` |
| 查看全部可公开代码和实验分类 | [`web-skill-factory-all`](https://github.com/DEM1TASSE/Webwright/tree/web-skill-factory-all) | All-code handoff；从 `VERSION_INDEX.md` 开始 |
| 复现同模板 Workflow baseline | [`590beeab`](https://github.com/DEM1TASSE/Webwright/tree/590beeab) | all 历史中的冻结 commit；不是正收益版本 |

## Primitive BEST

`web-skill-factory-best` 是 V12 direct primitive pipeline。它消费 V11 pipeline 自动生成的
audited library；没有手写 primitive。正式 WebArena template-disjoint T2 paired 结果：

| Arm | Success | Mean agent steps |
|---|---:|---:|
| Scratch | 93/156 (59.6%) | 13.20 |
| Primitive | 100/156 (64.1%) | 11.90 |
| Delta | **+4.5 pp** | **-9.8%** |

对应 tag 为 `web-skill-factory-best-v12`。权威说明和机器可读结果位于：

- `evals/webarena/primitive_v12_pipeline_review_zh-CN.md`
- `evals/webarena/reuse_split_v1_eval_results_v12_mixed_paired/summary.json`
- `evals/webarena/primitive_rt_v1_library_v11_public/`

## Workflow reference

`590beeab` 是 pre-cross-template workflow factory：用同一
template 的多个 gold-admitted instances 做参数和 pattern 泛化，输出 standalone workflow，
不 import primitive package。

它是冻结、可复现的 baseline，但不能标成正收益 BEST：

| Evaluation | Scratch | Workflow |
|---|---:|---:|
| T1 same-template | 44/70 (62.9%) | 42/70 (60.0%) |
| T2 cross-template adapt ablation | 43/59 (72.9%) | 33/59 (55.9%) |

Workflow 的意义是提供 same-template baseline 和 workflow-vs-primitive ablation；继续发布前
还需要单独开发。

## All-code 分支如何阅读

首先阅读
[`VERSION_INDEX.md`](https://github.com/DEM1TASSE/Webwright/blob/web-skill-factory-all/VERSION_INDEX.md)。
它将实验分成：

- `BEST`：可用于正式结果的 Primitive V12；
- `WORKFLOW REFERENCE`：冻结但没有准确率收益的 workflow baseline；
- `DEV`：V13–V18c，基于已分析过的 156-task development evidence；
- `HISTORICAL / ABLATION`：V4–V11、raw-script、workflow-adapt 等；
- `INVALID`：配置错误、wrong split、接口错误、污染运行等，禁止报告；
- `STRESS`：并发与基础设施测试，不是模型质量结果。

All-code 工作树以 BEST 实现为底，额外包含 official WebArena split/runner、WebVoyager、
Odysseys 和测试。互斥的历史实现通过 archival Git history 保留，而不是复制成多套可编辑
模块；因此该分支用于开发和审计，不是冻结 benchmark arm。

## Checkout

复现 BEST：

```bash
git clone --branch web-skill-factory-best https://github.com/DEM1TASSE/Webwright.git
```

获取全部可公开代码：

```bash
git clone --branch web-skill-factory-all https://github.com/DEM1TASSE/Webwright.git
```

获取冻结 workflow reference：

```bash
git clone https://github.com/DEM1TASSE/Webwright.git
cd Webwright
git checkout 590beeab
```

## 完整私有导出

GitHub 只保存代码、测试、安全的 library snapshot、compact results 和报告。以下内容不得
上传到公开仓库：

- raw trajectories、HAR、cookies 和登录截图；
- `.env`、PEM、API key、内部 endpoint 和 deployment credentials；
- 完整 run workspaces、浏览器状态和大型视频；
- 包含 source workflow 全文或真实账号证据的 private library index。

离开实验机器前，建议另外生成一个私有数据包，并生成完整 refs bundle：

```bash
git bundle create webwright-all-refs.bundle --all
git bundle verify webwright-all-refs.bundle
sha256sum webwright-all-refs.bundle > webwright-all-refs.bundle.sha256
```

私有数据包应按 `code/`、`data/`、`presentation/`、`metadata/`、`secrets/README.md`
组织；secret 本体通过批准的密钥管理渠道单独迁移。

## 发布纪律

1. Slide 和论文数字只引用 `BEST` 的冻结结果。
2. Workflow 目前称为 `reference/baseline`，不能声称有准确率收益。
3. DEV subset 的改进不能替代新的 untouched test。
4. 不从旧实验分支继续开发；新开发从 all-code 分支开始，正式复现从 BEST 开始。
5. 不机械 merge 旧实验分支。需要的通用修复经测试后 cherry-pick，并重新冻结结果。

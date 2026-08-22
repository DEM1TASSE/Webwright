# Minimal Effective V1：Workflow / Primitive / Scratch 实验快照（2026-08-21）

分支：`primitive-v12-cross-template-run-0821`  
协议对齐代码：`8a78474c0db8a6877160f2fdac82b1cbe32e575c`

本目录只保存小文件：逐题结果 JSON、split/runner manifest、Primitive library 的 index/audit/review 摘要和分析。**不包含 trajectory、截图、浏览器 profile 或其他大文件。**完整运行产物保存在机器上的 `/data/demiwang/EXPORT-2/minimal_effective_v1_0821/`。

## 1. 实验状态

### Official-protocol serial checkpoint

| 实验 | 目标 | 完成 | 剩余 | Correct | Incorrect | Evaluator infra error | Agent incomplete |
|---|---:|---:|---:|---:|---:|---:|---:|
| T1 same-template / Workflow exact | 117 | 110 | 7 | 55 | 45 | 9 | 1 |
| T2 cross-template / Primitive minimal | 188 | 96 | 92 | 46 | 39 | 11 | 0 |

这是机器停止前的**未完成 checkpoint**。Infrastructure error 不是模型失败，应该优先从已经捕获的 final state 重新判分。

### Earlier parallel checkpoint（旧 prompt/auth 协议，仅用于诊断）

| 配对子集 | Library arm | Scratch | 差值 |
|---|---:|---:|---:|
| T1 Workflow, 124 tasks | 77/124 = 62.1% | 85/124 = 68.5% | -6.5pp |
| T2 Primitive, 211 tasks | 124/211 = 58.8% | 124/211 = 58.8% | 0.0pp |

旧 parallel runner 向 agent 暴露了合成的 `RETRIEVE`/`agent_response.json` 协议，且没有与 official scratch 完全一致的 storage-state/evaluator auth 路径，因此不能作为最终正式结论。它仍可用于定位 domain 与 retrieval 问题。

## 2. 当前 official-protocol serial 子集与 Scratch 的配对比较

比较使用完全相同的已完成 task IDs。由于 serial run 在暂停时尚未完成，不同 domain 的进度极不均衡，下面是 provisional checkpoint，不是完整 held-out 分数。

### T1 Workflow vs Scratch（110 paired tasks）

| Domain | N | Workflow | Scratch | 差值 |
|---|---:|---:|---:|---:|
| GitLab | 42 | 1/42 = 2.4% | 22/42 = 52.4% | -50.0pp |
| Reddit | 22 | 18/22 = 81.8% | 19/22 = 86.4% | -4.5pp |
| Shopping | 20 | 16/20 = 80.0% | 12/20 = 60.0% | +20.0pp |
| Shopping Admin | 26 | 20/26 = 76.9% | 20/26 = 76.9% | 0.0pp |
| **Micro** | **110** | **55/110 = 50.0%** | **73/110 = 66.4%** | **-16.4pp** |
| **Macro（4 个已出现 domain 等权）** | | **60.3%** | **68.9%** | **-8.6pp** |

T1 的主要异常集中在 GitLab。该 checkpoint 还包含 9 个 evaluator infrastructure errors；需要先重判，再分析 Workflow 本身的失败。

### T2 Primitive vs Scratch（96 paired tasks）

| Domain | N | Primitive | Scratch | 差值 |
|---|---:|---:|---:|---:|
| GitLab | 66 | 33/66 = 50.0% | 37/66 = 56.1% | -6.1pp |
| Reddit | 29 | 13/29 = 44.8% | 14/29 = 48.3% | -3.4pp |
| Shopping | 1 | 0/1 = 0.0% | 1/1 = 100% | -100pp |
| **Micro** | **96** | **46/96 = 47.9%** | **52/96 = 54.2%** | **-6.3pp** |
| **Macro（3 个已出现 domain 等权）** | | **31.6%** | **68.1%** | **-36.5pp** |

T2 macro 暂时没有解释价值：Shopping 只有 1 题，Map、Shopping Admin、Wikipedia 尚未进入这个 serial checkpoint。Micro 也只是未完成子集上的 provisional 数字。

T2 routing 分布：`skip=74`、`adapt=17`、`use=5`。也就是 77.1% 的已完成 serial tasks 没有实际注入 Primitive；当前结果更接近保守 routing 下的 scratch-like arm，而不是充分使用 library 的结果。

## 3. 旧 parallel 子集的 domain 配对分析

### T1 Workflow（124 tasks）

| Domain | Workflow | Scratch | 差值 |
|---|---:|---:|---:|
| GitLab | 8/16 = 50.0% | 7/16 = 43.8% | +6.2pp |
| Map | 16/26 = 61.5% | 21/26 = 80.8% | -19.2pp |
| Reddit | 3/3 = 100% | 3/3 = 100% | 0 |
| Shopping | 25/37 = 67.6% | 25/37 = 67.6% | 0 |
| Shopping Admin | 21/35 = 60.0% | 25/35 = 71.4% | -11.4pp |
| Wikipedia | 4/7 = 57.1% | 4/7 = 57.1% | 0 |

Micro：62.1% vs 68.5%（-6.5pp）。  
Macro：66.0% vs 70.1%（-4.1pp）。

### T2 Primitive（211 tasks）

| Domain | Primitive | Scratch | 差值 |
|---|---:|---:|---:|
| GitLab | 17/33 = 51.5% | 18/33 = 54.5% | -3.0pp |
| Map | 38/57 = 66.7% | 35/57 = 61.4% | +5.3pp |
| Reddit | 2/4 = 50.0% | 2/4 = 50.0% | 0 |
| Shopping | 30/61 = 49.2% | 32/61 = 52.5% | -3.3pp |
| Shopping Admin | 33/51 = 64.7% | 33/51 = 64.7% | 0 |
| Wikipedia | 4/5 = 80.0% | 4/5 = 80.0% | 0 |

Micro：58.8% vs 58.8%（0.0pp）。  
Macro：60.3% vs 60.5%（-0.2pp）。

## 4. Frozen Primitive library

| Domain | Final primitives |
|---|---:|
| GitLab | 39 |
| Map | 10 |
| Reddit | 28 |
| Shopping | 51 |
| Shopping Admin | 48 |
| Wikipedia | 0 |
| **Total** | **176** |

`t2_primitive/library_summary/` 保存每个 domain 的 `index.json`、`audit.json` 和 `review.md`。完整可执行 package 没有复制到这个 compact results package；它仍在 frozen library 和 `/data` 导出中。

## 5. 文件结构

- `t1_workflow/results/`: T1 逐题小结果文件（124 parallel + 110 serial = 234）
- `t1_workflow/manifest/`: same-template manifest 与 workflow coverage IDs
- `t2_primitive/results/`: T2 逐题小结果文件（211 parallel + 96 serial = 307）
- `t2_primitive/manifest/`: cross-template manifest 与 serial IDs
- `t2_primitive/library_summary/`: frozen Primitive library 的 compact metadata/audit/review

所有 541 个结果 JSON 均可解析。Trajectory 数量和大文件只保存在 `/data` export，不进入 GitHub。

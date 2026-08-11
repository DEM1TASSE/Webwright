# WebVoyager scratch/routed 基础设施

该目录直接读取官方 `data/WebVoyager_data.jsonl`，支持单任务 scratch/routed 运行、原始
WebVoyager outcome-judge protocol、结果物化和 paired comparison。

## 1. Dry-run

```bash
export WV_DATA=/path/to/WebVoyager/data/WebVoyager_data.jsonl
export TASK_ID=GitHub--0
export RUN_ROOT=/tmp/webvoyager-pilot

python evals/webvoyager/pipeline.py solve "$TASK_ID" scratch \
  --dataset "$WV_DATA" --runs "$RUN_ROOT/scratch" -c model_gateway.yaml --dry-run

python evals/webvoyager/pipeline.py solve "$TASK_ID" routed \
  --dataset "$WV_DATA" --runs "$RUN_ROOT/routed" \
  --library "$RUN_ROOT/library" -c model_gateway.yaml --dry-run
```

实际运行 routed 前，还要设置 primitive router 使用的模型；browser agent 的 YAML 不会自动
配置 router：

```bash
export SKILL_MODEL_ENDPOINT=https://your-gateway.example/v1/responses
export SKILL_MODEL_NAME=your-model
```

运行前应先冻结并验证人工 template/capability 标注：

```bash
python evals/webvoyager/validate_split.py \
  --dataset "$WV_DATA" --manifest evals/webvoyager/split.example.json
```

Validator 检查 task ID 是否存在、source/held-out 是否重复、任务是否属于声明站点，并报告
family overlap 与 capability overlap。`split.example.json` 只是格式示例，不是正式实验 split。

## 2. Judge

Evaluator 复现 WebVoyager 的任务 + final response + 最后 k 张截图协议，但通过 Responses API
调用可配置的 multimodal model：

```bash
python -m webwright.skill_factory webvoyager-eval \
  --trajectories-dir "$RUN_ROOT/scratch" --tasks-file "$WV_DATA" \
  --output "$RUN_ROOT/scratch.judge.jsonl" --mode scratch \
  --model gpt-4o --max-images 15

python -m webwright.skill_factory webvoyager-eval \
  --trajectories-dir "$RUN_ROOT/routed" --tasks-file "$WV_DATA" \
  --output "$RUN_ROOT/routed.judge.jsonl" --mode routed \
  --model gpt-4o --max-images 15
```

## 3. 从准入 source 建 primitive library

先人工冻结并标注 source 的 capability family，再只传入 Judge 接纳的任务：

```bash
python evals/webvoyager/build_generated_primitives.py \
  --dataset "$WV_DATA" --runs "$RUN_ROOT/source" \
  --judge-results "$RUN_ROOT/source.judge.jsonl" \
  --library "$RUN_ROOT/library" --report "$RUN_ROOT/build-report.json" \
  --source GitHub--0=repo_search_and_rank \
  --source GitHub--14=repo_contributor_lookup
```

Builder 延续当前的保守准入要求：一个新增 primitive 必须得到至少两个不同 source family 的
支持，且所有 source trajectory 必须已通过 Judge。

## 4. 物化与比较

```bash
python evals/webvoyager/pipeline.py materialize "$TASK_ID" scratch \
  --dataset "$WV_DATA" --runs "$RUN_ROOT/scratch" \
  --judge-results "$RUN_ROOT/scratch.judge.jsonl" --output "$RUN_ROOT/scratch.json"

python evals/webvoyager/pipeline.py materialize "$TASK_ID" routed \
  --dataset "$WV_DATA" --runs "$RUN_ROOT/routed" \
  --judge-results "$RUN_ROOT/routed.judge.jsonl" --output "$RUN_ROOT/routed.json"

python evals/webvoyager/pipeline.py compare \
  --scratch "$RUN_ROOT/scratch.json" --routed "$RUN_ROOT/routed.json" \
  --output "$RUN_ROOT/summary.json"
```

结果显式区分：

- `primitive_selected`：metadata gate 是否注入了 primitive。
- `primitive_used`：agent 是否在 `primitive_usage.json` 中声明实际使用。
- `routed_correct`：整个 routed pipeline 是否成功，不能单独解释为 primitive 效果。

缺失或无法解析的 Judge verdict 物化为 `correct: null`，不会静默计为失败。

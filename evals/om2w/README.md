# Online-Mind2Web single-task smoke test

For the current implementation status, five-site pilot findings, and a task-level comparison with
WebVoyager, see [`docs/skill_factory/online_mind2web_webvoyager.md`](../../docs/skill_factory/online_mind2web_webvoyager.md).

The smoke pipeline intentionally separates live website solves from WebJudge calls. Replace the
example task ID as needed; no frozen subset is required.

```bash
export DATASET=/home/t-demiwang/Online-Mind2Web/Online_Mind2Web.json
export TASK_ID=4e0f5561a76478da87995dee00b09572
export SMOKE=/tmp/om2w-smoke

# Inspect commands without launching a model or browser.
python evals/om2w/smoke_pipeline.py solve "$TASK_ID" scratch \
  --dataset "$DATASET" --runs "$SMOKE/scratch" -c model_gateway.yaml --dry-run
python evals/om2w/smoke_pipeline.py solve "$TASK_ID" routed \
  --dataset "$DATASET" --runs "$SMOKE/routed" --library "$SMOKE/library" \
  -c model_gateway.yaml --dry-run

# Remove --dry-run to launch each arm. Then judge each arm independently.
python -m webwright.skill_factory om2w-eval \
  --trajectories-dir "$SMOKE/scratch" --tasks-file "$DATASET" \
  --upstream-src /path/to/Online-Mind2Web/src --output "$SMOKE/scratch.judge.jsonl" \
  --mode scratch --model o4-mini
python -m webwright.skill_factory om2w-eval \
  --trajectories-dir "$SMOKE/routed" --tasks-file "$DATASET" \
  --upstream-src /path/to/Online-Mind2Web/src --output "$SMOKE/routed.judge.jsonl" \
  --mode routed --model o4-mini

python evals/om2w/smoke_pipeline.py materialize "$TASK_ID" scratch \
  --dataset "$DATASET" --runs "$SMOKE/scratch" \
  --judge-results "$SMOKE/scratch.judge.jsonl" --output "$SMOKE/scratch.json"
python evals/om2w/smoke_pipeline.py materialize "$TASK_ID" routed \
  --dataset "$DATASET" --runs "$SMOKE/routed" \
  --judge-results "$SMOKE/routed.judge.jsonl" --output "$SMOKE/routed.json"
python evals/om2w/smoke_pipeline.py compare \
  --scratch "$SMOKE/scratch.json" --routed "$SMOKE/routed.json" \
  --output "$SMOKE/summary.json"
```

A missing or invalid judge verdict is materialized as `correct: null` with
`run_status: evaluator_infrastructure_error`; it is never counted as an agent failure or silently
dropped. An empty routed library is useful only for plumbing validation and does not test reuse.

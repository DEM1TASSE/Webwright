#!/usr/bin/env bash
# One arm (asi | scratch) of the cross-template held-out evaluation on instance 4.
#
# lanes.md §4 puts the two lanes on separate instances so the write lane cannot pollute
# the read lane. Only instance 4 is available here, so they are sequenced instead:
# the read-only lane runs FIRST on a pristine instance and writes nothing, so the write
# lane that follows it starts from the same pristine state. A reset is required between
# ARMS, not between lanes -- run reset_inst4.sh before each arm.
#
# Concurrency follows lanes.md §8, which measured contention masquerading as task
# timeouts: the read lane went 64 -> 8 and every timed-out task then passed in 172-512s;
# the write lane went 24 -> 6 and hit zero timeouts.
#
# site_lanes() builds per_site_workers lanes for EACH site and hands them all to one
# pool of --workers threads, so --workers must exceed per_site_workers x sites or the
# first site's lanes fill every thread and starve the rest -- the failure lanes.md
# section 3 describes. 8 per site over 6 sites needs 48 global.
set -euo pipefail
ARM="${1:-}"
[ "$ARM" = asi ] || [ "$ARM" = scratch ] || { echo "usage: run_arm.sh asi|scratch" >&2; exit 2; }
REPO=/home/t-demiwang/webwright-primitive-v12-cross-template
ROOT=/data/demiwang/results/webarena/ww_asi
M=/data/demiwang/results/webarena/minimal_effective_v1/manifests/cross_template
PY=/data/ww_official/webwright/.venv/bin/python

set -a; . /home/t-demiwang/.env; set +a
# The official evaluator's llm_fuzzy_match goes through evaluation_harness/helper_functions.py,
# which sets openai.api_key from the environment and otherwise talks to the DEFAULT OpenAI
# endpoint. Without a base URL the gateway key is sent to api.openai.com and every fuzzy-matched
# task dies as `evaluator_infrastructure_error` (HTTP 401) -- 32 of them before this was set.
# ~/.env carries only the key; the base URL has to come from here.
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://gateway.phyagi.net/api}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-$OPENAI_BASE_URL}"
cd "$REPO"

common=(
  --partition t2 --arm "$ARM"
  --split "$M/runner/reuse_split.json"
  --dataset /data/ww_official/webarena_official/config_files/test.raw.json
  --config /data/ww_official/deployment_inst4.json
  --runs-root "$ROOT/$ARM/runs" --results-root "$ROOT/$ARM/results"
  --workflow-events "$ROOT/$ARM/workflow_events.json"
  --model-config evals/webarena/model.gateway54.yaml
  --eval-python /data/ww_official/webwright/.venv/bin/python
  --webarena-tasks /data/ww_official/webarena_official/config_files/test.raw.json
  --webarena-root /data/ww_official/webarena_official
  --timeout 900
)

# run_reuse_eval exits 1 when ANY task ended in process_error. That is an ordinary partial
# outcome, not a reason to skip the write lane -- `set -e` silently did exactly that on the
# 21:29 run, which finished the read lane and then stopped without touching the 188 mutate tasks.
echo "=== $ARM: read-only lane (211 tasks, 8 per site, 48 global) ==="
$PY evals/webarena/run_reuse_eval.py "${common[@]}" \
    --task-ids-file "$M/parallel_ids.json" \
    --workers 48 --per-site-workers 8 \
    2>&1 | tee -a "$ROOT/$ARM.parallel.log" || echo "read lane exited $? (partial failures are expected; continuing)"

echo "=== $ARM: write lane (188 tasks, 61 scope chains, 6 workers) ==="
$PY evals/webarena/run_reuse_eval.py "${common[@]}" \
    --task-ids-file "$M/serial_ids.json" \
    --serial-groups "$ROOT/serial_groups_test399.json" \
    --workers 6 \
    2>&1 | tee -a "$ROOT/$ARM.serial.log" || echo "write lane exited $? (partial failures are expected)"

echo "=== $ARM done ==="

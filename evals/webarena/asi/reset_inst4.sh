#!/usr/bin/env bash
# Reset WebArena instance 4 for the ASI / scratch arms.
# Order is lanes.md §6 verbatim; step 4 (auth regen) is dropped because the
# cross_task_eval path never reads storage_state -- the agent logs in from the
# plaintext credentials in its prompt.
set -euo pipefail
K=4
WW=/data/ww_official/webwright
DEP=/data/ww_official/deployment_inst4.json
PY=$WW/.venv/bin/python

echo "[1/4] rebuilding containers for instance $K"
bash /data/webarena/replica.sh reset $K

echo "[2/4] waiting for every site to actually serve (WAL replay outlasts nginx 200)"
$PY $WW/skills/official-webarena/scripts/deployment_state.py \
    --instance $K --deployment-config $DEP --wait 2400

echo "[3/4] waiting for postmill postgres to accept connections"
until docker exec forum_$K psql -U postgres -d postmill -c 'SELECT 1' >/dev/null 2>&1; do
  sleep 30; echo "    ... still replaying"
done

echo "[4/4] fingerprint check against pristine"
$PY $WW/skills/official-webarena/scripts/deployment_state.py \
    --instance $K --deployment-config $DEP \
    --verify /data/ww_official/pristine_fingerprint.json

echo "instance $K ready"

#!/bin/bash
# Phase 2-4: reset instance 1, prove it is pristine and serving, then replay the frozen
# scripts against it. Each gate refuses rather than proceeds, because every failure mode
# here is silent -- a site that is not up and a reset that did not take both show up only
# as a lower score.
set -u
LOG=/data/ww_official/replay_phase.log
S=/data/ww_official/webwright/skills/official-webarena/scripts
say(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

say "PHASE 1 等待生成结束 (pid 3890707)"
while kill -0 3890707 2>/dev/null; do sleep 60; done
say "PHASE 1 结束"
date +%s > /data/ww_official/.phase1_end

# A task that timed out produced no final_script.py, so the replay phase would have nothing to
# run for it and would score it zero twice over. On the read-only lane every one of these
# recovered once the concurrency came down -- they finished in 172-512s against a 900s cap, so
# what ran out was contention, not the task. Retry them here, while the site still holds the
# state they were generated against; after the reset this would no longer be a generation.
say "PHASE 1b 补跑超时的生成任务"
cd /data/ww_official
TO=$(python3 -c "
import json
rows={}
for line in open('/data/ww_official/mutate_progress.jsonl'):
    try: r=json.loads(line)
    except Exception: continue
    if 'task_id' in r: rows[r['task_id']]=r
print(' '.join('--task-id %d' % t for t,r in sorted(rows.items()) if r.get('timed_out')))
")
say "PHASE 1b 待补: ${TO:-无}"
if [ -n "$TO" ]; then
  set -a; . ./env.sh; export OPENAI_API_BASE="$OPENAI_BASE_URL" NLTK_DATA=/home/t-demiwang/nltk_data \
    WEBARENA_LOGIN_PYTHON=/home/t-demiwang/agent-skill-induction/.venv/bin/python \
    SHOPPING="http://gcrsandbox410.redmond.corp.microsoft.com:7870" \
    SHOPPING_ADMIN="http://gcrsandbox410.redmond.corp.microsoft.com:7880/admin" \
    REDDIT="http://gcrsandbox410.redmond.corp.microsoft.com:10099" \
    GITLAB="http://gcrsandbox410.redmond.corp.microsoft.com:8123" \
    WIKIPEDIA="http://gcrsandbox410.redmond.corp.microsoft.com:8988/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing" \
    HOMEPAGE="http://gcrsandbox410.redmond.corp.microsoft.com:4499" \
    MAP="http://gcrsandbox410.redmond.corp.microsoft.com:3000"; set +a
  webwright/.venv/bin/python run_official.py \
    --webarena-root /data/ww_official/webarena_official \
    --deployment-config /data/ww_official/deployment_inst1.json \
    --task-ids /data/ww_official/partition/serial_ids.json \
    --serial-groups /data/ww_official/partition/serial_groups.json \
    --output-root /data/ww_official/mutate_runs --results-root /data/ww_official/mutate_results \
    --model-config /home/t-demiwang/Code-Web-Skills/code/configs/model_gateway_54.yaml \
    --workers 6 --timeout 1500 $TO \
    --progress /data/ww_official/mutate_progress.jsonl >> /data/ww_official/mutate_retry.log 2>&1
fi
say "PHASE 1b 结束"

say "PHASE 2 重置 instance 1"
bash /data/webarena/replica.sh reset 1 >> /data/webarena/reset_inst1_phase2.log 2>&1
say "PHASE 2 replica.sh 返回"

say "PHASE 3a 等待站点真正在服务"
python3 "$S/deployment_state.py" --instance 1 \
  --deployment-config /data/ww_official/deployment_inst1.json --wait 2400 >> "$LOG" 2>&1 \
  || { say "站点未就绪,中止"; exit 1; }
# Postmill answers 200 from nginx while Postgres is still replaying its WAL, so serving is
# not enough on its own; the database has to accept a query before anything is measured.
for i in $(seq 1 80); do
  docker exec forum_1 psql -U postgres -d postmill -t -A -c "SELECT 1" >/dev/null 2>&1 && break
  sleep 30
done
say "PHASE 3a 站点就绪"

say "PHASE 3b 重新生成 auth (reset 清掉了服务端 session)"
cd /data/ww_official/webarena_official
export SHOPPING="http://gcrsandbox410.redmond.corp.microsoft.com:7870" \
  SHOPPING_ADMIN="http://gcrsandbox410.redmond.corp.microsoft.com:7880/admin" \
  REDDIT="http://gcrsandbox410.redmond.corp.microsoft.com:10099" \
  GITLAB="http://gcrsandbox410.redmond.corp.microsoft.com:8123" \
  WIKIPEDIA="http://gcrsandbox410.redmond.corp.microsoft.com:8988/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing" \
  HOMEPAGE="http://gcrsandbox410.redmond.corp.microsoft.com:4499" \
  MAP="http://gcrsandbox410.redmond.corp.microsoft.com:3000" \
  PYTHONPATH=/data/ww_official/webarena_official
/home/t-demiwang/agent-skill-induction/.venv/bin/python -c "
from browser_env.auto_login import renew_comb
for comb in (['shopping'],['shopping_admin'],['reddit'],['gitlab'],['gitlab','reddit']):
    renew_comb(sorted(comb), auth_folder='/data/ww_official/.auth_inst1')
    print('auth ok', '.'.join(sorted(comb)), flush=True)
" >> "$LOG" 2>&1 || { say "auth 生成失败,中止"; exit 1; }
say "PHASE 3b auth 就绪"

say "PHASE 3c 指纹校验"
python3 "$S/deployment_state.py" --instance 1 \
  --verify /data/ww_official/pristine_fingerprint.json >> "$LOG" 2>&1 \
  || { say "指纹漂移,拒绝开跑 PHASE 4"; exit 1; }
say "PHASE 3c 确认纯净"

say "PHASE 4 按序重放"
date +%s > /data/ww_official/.phase4_start
cd /data/ww_official
set -a; . ./env.sh; export OPENAI_API_BASE="$OPENAI_BASE_URL" NLTK_DATA=/home/t-demiwang/nltk_data \
  WEBARENA_LOGIN_PYTHON=/home/t-demiwang/agent-skill-induction/.venv/bin/python; set +a
webwright/.venv/bin/python run_official.py \
  --webarena-root /data/ww_official/webarena_official \
  --deployment-config /data/ww_official/deployment_inst1.json \
  --task-ids /data/ww_official/partition/serial_ids.json \
  --serial-groups /data/ww_official/partition/serial_groups.json \
  --output-root /data/ww_official/mutate_runs \
  --results-root /data/ww_official/mutate_results \
  --replay-results-root /data/ww_official/mutate_results_replay \
  --model-config /home/t-demiwang/Code-Web-Skills/code/configs/model_gateway_54.yaml \
  --replay-only --workers 24 --replay-timeout 600 \
  --progress /data/ww_official/replay_progress.jsonl >> /data/ww_official/replay.log 2>&1
date +%s > /data/ww_official/.phase4_end
say "PHASE 4 结束"

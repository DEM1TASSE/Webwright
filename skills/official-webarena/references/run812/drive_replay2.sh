#!/bin/bash
# Phase 4b: replay the whole set again, this time against a deployment that has been warmed
# and at a concurrency the sites can absorb.
#
# The first replay ran two minutes after GitLab and Magento were recreated, at 24 concurrent
# scripts. Playwright's per-action timeout is 30s, two orders of magnitude tighter than the
# 900s the generation phase allowed, so a cold heavy admin page fails the whole script rather
# than merely running slowly. Twice already in this batch a timeout that looked like task
# difficulty turned out to be contention and cleared entirely when the concurrency came down.
#
# Re-running needs its own reset: a replay writes to the site exactly as the generation did,
# so the second pass has to start from the same pristine state as the first.
set -u
LOG=/data/ww_official/replay_phase.log
S=/data/ww_official/webwright/skills/official-webarena/scripts
say(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

say "PHASE 4b 等待第一次重放结束"
while pgrep -f 'replay-results-root /data/ww_official/mutate_results_replay' >/dev/null; do sleep 30; done
mv /data/ww_official/mutate_results_replay /data/ww_official/mutate_results_replay_pass1
say "PHASE 4b 第一次结果已归档为 mutate_results_replay_pass1"

say "PHASE 4b 重置 instance 1"
bash /data/webarena/replica.sh reset 1 >> /data/webarena/reset_inst1_phase4b.log 2>&1

say "PHASE 4b 等待站点就绪"
python3 "$S/deployment_state.py" --instance 1 \
  --deployment-config /data/ww_official/deployment_inst1.json --wait 2400 >> "$LOG" 2>&1 \
  || { say "站点未就绪,中止"; exit 1; }
for i in $(seq 1 80); do
  docker exec forum_1 psql -U postgres -d postmill -t -A -c "SELECT 1" >/dev/null 2>&1 && break
  sleep 30
done

# Warm the pages the scripts hit hardest. Magento renders its admin grids on first request and
# GitLab compiles assets lazily; the first caller pays for both, and under the first replay that
# caller was a task being scored.
say "PHASE 4b 预热站点"
for u in "http://gcrsandbox410.redmond.corp.microsoft.com:7880/admin" \
         "http://gcrsandbox410.redmond.corp.microsoft.com:7870" \
         "http://gcrsandbox410.redmond.corp.microsoft.com:8123/explore" \
         "http://gcrsandbox410.redmond.corp.microsoft.com:10099"; do
  for _ in 1 2 3; do curl -s -o /dev/null -m 60 "$u"; done
done

say "PHASE 4b 重新生成 auth"
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
    renew_comb(sorted(comb), auth_folder='/data/ww_official/.auth_inst1'); print('auth ok','.'.join(sorted(comb)),flush=True)
" >> "$LOG" 2>&1 || { say "auth 失败,中止"; exit 1; }

say "PHASE 4b 指纹校验"
python3 "$S/deployment_state.py" --instance 1 \
  --verify /data/ww_official/pristine_fingerprint.json >> "$LOG" 2>&1 \
  || { say "指纹漂移,拒绝开跑"; exit 1; }
say "PHASE 4b 确认纯净"

say "PHASE 4b 低并发全量重放"
cd /data/ww_official
set -a; . ./env.sh; export OPENAI_API_BASE="$OPENAI_BASE_URL" NLTK_DATA=/home/t-demiwang/nltk_data \
  WEBARENA_LOGIN_PYTHON=/home/t-demiwang/agent-skill-induction/.venv/bin/python; set +a
webwright/.venv/bin/python run_official.py \
  --webarena-root /data/ww_official/webarena_official \
  --deployment-config /data/ww_official/deployment_inst1.json \
  --task-ids /data/ww_official/partition/serial_ids.json \
  --serial-groups /data/ww_official/partition/serial_groups.json \
  --output-root /data/ww_official/mutate_runs --results-root /data/ww_official/mutate_results \
  --replay-results-root /data/ww_official/mutate_results_replay \
  --model-config /home/t-demiwang/Code-Web-Skills/code/configs/model_gateway_54.yaml \
  --replay-only --workers 6 --replay-timeout 900 \
  --progress /data/ww_official/replay2_progress.jsonl >> /data/ww_official/replay2.log 2>&1
say "PHASE 4b 结束"

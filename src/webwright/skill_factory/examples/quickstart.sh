#!/usr/bin/env bash
# One-command Quickstart — every parameter pre-filled, nothing to write.
#
#   ./quickstart.sh                      # instant: run the checked-in flight skill, NO model, no key
#   ./quickstart.sh run LAX ORD          # ...on YOUR route (any airport codes, default date)
#   ./quickstart.sh run LAX ORD 2026-09-01   # ...and YOUR date
#   ./quickstart.sh route    # route a task the skill CAN'T run as-is -> it escalates to the agent (needs OPENAI_API_KEY)
#   ./quickstart.sh solve    # one agent solve that REUSES the checked-in skill (needs key)
#
# The whole loop from nothing is a spec now, not a mode of this script — it is the same
# 3 solves -> learn, but parallel, resumable, and it shows you the plan first:
#   python -m webwright.skill_factory build flights.skill.yaml --library ./library --jobs 3
#
# Custom / OpenAI-compatible gateway? One knob:
#   export OPENAI_ENDPOINT=... OPENAI_MODEL=...   (everything here, agent included)
#   MODEL_CFG=/abs/model.yaml is optional, for putting the AGENT on a different model.
set -euo pipefail
SELF="$(readlink -f "$0")"
cd "$(dirname "$SELF")"
DATE=$(date -d "+30 days" +%Y-%m-%d 2>/dev/null || date -v+30d +%Y-%m-%d)
WORK="${QUICKSTART_WORKDIR:-$(mktemp -d /tmp/skills_quickstart.XXXX)}"
LIB="$PWD/learned_library"
# The AGENT's model comes from a yaml and never reads OPENAI_*, so a gateway you exported would
# send `ask` there and this script's solves to api.openai.com. Pass your env along as inline
# `-c model.key=value` overrides instead — same thing build does, no yaml for you to write.
# MODEL_CFG still wins, for the day the agent wants a different model than the distiller.
if [ -n "${MODEL_CFG:-}" ]; then
  CFG=(-c base.yaml -c "$MODEL_CFG")
else
  CFG=(-c base.yaml -c model_openai.yaml)
  [ -n "${OPENAI_ENDPOINT:-}" ] && CFG+=(-c "model.openai_endpoint=$OPENAI_ENDPOINT")
  [ -n "${OPENAI_MODEL:-}" ]    && CFG+=(-c "model.model_name=$OPENAI_MODEL")
  # base.yaml caps the agent at 4000 output tokens; reusing a large skill needs more, or the
  # agent's script is truncated mid-write and the run loops. The gateway yaml set 16000; match it.
  CFG+=(-c "model.max_output_tokens=${SKILL_AGENT_MAX_TOKENS:-16000}")
fi

need_key() { : "${OPENAI_API_KEY:?export OPENAI_API_KEY first (on a gateway also OPENAI_ENDPOINT / OPENAI_MODEL)}"; }


flight_task() { # $1 "City (CODE)"  $2 "City (CODE)"
  echo "What is the earliest nonstop flight from $1 to $2 on $DATE (one-way)? Return the answer as a list: [flight_number, airline, departure_time], e.g. [\"AS 336\", \"Alaska\", \"6:00 AM\"]."
}

# The skill drives the site by airport CODE; the *_city params exist in its signature but are
# unused here, so you only ever type the codes. A generated skill is a plain CLI: pass the
# parameters as --flags. (It still also accepts `skill.py taskspec.json`, which is what replay
# and programmatic callers use — the flags are just the human-facing form of the same inputs.)

case "${1:-run}" in
run)
  FROM="${2:-SEA}"; TO="${3:-DEN}"; ON="${4:-$DATE}"
  echo "== the checked-in flight skill, standalone: earliest nonstop $FROM->$TO on $ON (no model, ~40 s) =="
  # only pitch the custom-route form when the user hasn't already given one
  [ $# -ge 3 ] || echo "   (try your own route: $0 run LAX ORD 2026-09-01)"
  case "$ON" in
    [0-9][0-9][0-9][0-9]-[0-9]*-[0-9]*) ;;
    *) echo "!! date must be YYYY-MM-DD (e.g. 2026-09-01), got: $ON" >&2; exit 1 ;;
  esac
  SKILL="$(ls -d "$LIB"/what_is_the_earliest_nonstop_flight_*)/skill.py"
  echo "   \$ python skill.py --origin-city $FROM --origin-code $FROM --destination-city $TO --destination-code $TO --date $ON"
  (cd "$WORK" && WORKSPACE_DIR="$WORK" python "$SKILL" \
     --origin-city "$FROM" --origin-code "$FROM" \
     --destination-city "$TO" --destination-code "$TO" --date "$ON" > run.log 2>&1) \
     || { tail -5 "$WORK/run.log"; exit 1; }
  echo
  echo "-- what it did (no model chose these steps — they are the skill's code) --"
  sed -n 's/^\(step [0-9]*:\)/  \1/p' "$WORK"/runs/run_*/skill_log.txt 2>/dev/null || true
  echo
  echo "answer: $(cat "$WORK/agent_response.json")"
  SHOTS=$(ls "$WORK"/runs/run_*/screenshots/*.png 2>/dev/null | wc -l)
  echo "evidence: $SHOTS screenshots + step log ->"
  echo "  $(ls -d "$WORK"/runs/run_* 2>/dev/null | head -1)"
  echo "-> a learned skill just drove the live site with ZERO tokens. Next: $0 route | solve"
  ;;
route)
  need_key
  # A task the checked-in skill CANNOT run as-is: it finds the EARLIEST nonstop, this asks for the
  # SHORTEST-DURATION nonstop. Same site, same route/date slots, nonstop preserved — only the final
  # SELECTION differs (earliest departure -> shortest duration). So the router should NOT run it
  # directly; it should recognise that and hand the task to the agent to ADAPT. Declining to run
  # when it shouldn't is the point.
  TASK="What is the nonstop flight with the shortest flight duration from Seattle (SEA) to Denver (DEN) on $DATE (one-way)? Return the answer as a list: [flight_number, airline, duration]."
  echo "== routing a task the skill can't do as-is: SHORTEST-DURATION nonstop (the skill finds the EARLIEST) =="
  python -m webwright.skill_factory route --task "$TASK" --library "$LIB"
  echo "-> the router used the skill's grade + template to decide run-vs-agent BEFORE spending an agent. Next: $0 solve"
  ;;
solve)
  need_key
  # Same SHORTEST-DURATION-nonstop task the `route` mode inspected — now actually carry the decision
  # out. route finds the skill, judges it can't run as-is (shortest duration vs earliest), and
  # (because --start-url is given) LAUNCHES the agent to adapt it. Had the task been a plain
  # earliest-nonstop route, route would instead have run the skill directly with no agent at all.
  TASK="What is the nonstop flight with the shortest flight duration from Seattle (SEA) to Denver (DEN) on $DATE (one-way)? Return the answer as a list: [flight_number, airline, duration]."
  echo "== route + launch: route decides, then hands this shortest-duration task to the agent to ADAPT the skill =="
  python -m webwright.skill_factory route --task "$TASK" --library "$LIB" \
    --start-url https://www.google.com/flights -o "$WORK/outputs" --task-id qs_solve "${CFG[@]}"
  echo "answer: $(cat "$WORK"/outputs/qs_solve_*/agent_response.json 2>/dev/null || echo '(missing)')"
  ;;
*)
  # print the whole header comment — robust to edits, unlike a fixed line range
  awk 'NR>1 && /^#/ {print; next} NR>1 {exit}' "$SELF"; exit 1
  ;;
esac
echo "(work dir: $WORK)"

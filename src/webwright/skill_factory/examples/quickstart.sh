#!/usr/bin/env bash
# One-command Quickstart — every parameter pre-filled, nothing to write.
#
#   ./quickstart.sh                      # instant: run the checked-in flight skill, NO model, no key
#   ./quickstart.sh demo LAX ORD         # ...on YOUR route (any airport codes, default date)
#   ./quickstart.sh demo LAX ORD 2026-09-01   # ...and YOUR date
#   ./quickstart.sh ask      # ask the library about a new task    (needs OPENAI_API_KEY)
#   ./quickstart.sh solve    # one agent solve that REUSES the checked-in skill (needs key)
#
# The whole loop from nothing is a spec now, not a mode of this script — it is the same
# 3 solves -> learn, but parallel, resumable, and it shows you the plan first:
#   python -m webwright.skill_factory build flights.skill.yaml --library ./library --jobs 3
#
# Custom / OpenAI-compatible gateway? Two knobs, both needed:
#   export OPENAI_ENDPOINT=... OPENAI_MODEL=...   (for learn / skill_use)
#   export MODEL_CFG=/path/to/your_model.yaml     (for the agent in solve/build — copy
#     model_openai.yaml and set openai_endpoint/model_name; env vars do NOT reach it)
set -euo pipefail
SELF="$(readlink -f "$0")"
cd "$(dirname "$SELF")"
DATE=$(date -d "+30 days" +%Y-%m-%d 2>/dev/null || date -v+30d +%Y-%m-%d)
WORK="${QUICKSTART_WORKDIR:-$(mktemp -d /tmp/skills_quickstart.XXXX)}"
LIB="$PWD/learned_library"
CFG=(-c base.yaml -c "${MODEL_CFG:-model_openai.yaml}")

need_key() { : "${OPENAI_API_KEY:?export OPENAI_API_KEY first (on a gateway also OPENAI_ENDPOINT / OPENAI_MODEL)}"; }

warn_gateway_agent() {  # solve: the AGENT reads its yaml, not the env vars
  if [ -n "${OPENAI_ENDPOINT:-}" ] && [ -z "${MODEL_CFG:-}" ]; then
    echo "!! OPENAI_ENDPOINT is set but MODEL_CFG is not." >&2
    echo "!! learn/ask will use your gateway, but the AGENT in this mode reads a yaml" >&2
    echo "!! and will hit api.openai.com. Copy model_gateway.example.yaml, fill in your" >&2
    echo "!! endpoint (the FULL .../responses URL), then: export MODEL_CFG=/abs/path.yaml" >&2
  fi
}

flight_task() { # $1 "City (CODE)"  $2 "City (CODE)"
  echo "What is the earliest nonstop flight from $1 to $2 on $DATE (one-way)? Return the answer as a list: [flight_number, airline, departure_time], e.g. [\"AS 336\", \"Alaska\", \"6:00 AM\"]."
}

spec() { # $1 code $2 code $3 date -> taskspec.json in $WORK. The skill drives the site by
         # airport CODE; the *_city params are required by its signature but unused, so the
         # code doubles as the city and you only ever type the codes.
  cat > "$WORK/taskspec.json" <<EOF
{"params": {"origin_city": "$1", "origin_code": "$1", "destination_city": "$2",
            "destination_code": "$2", "date": "$3"},
 "output_schema": {"type": "array", "items": {"type": "string"}}}
EOF
}

case "${1:-demo}" in
demo)
  FROM="${2:-SEA}"; TO="${3:-DEN}"; ON="${4:-$DATE}"
  echo "== the checked-in flight skill, standalone: earliest nonstop $FROM->$TO on $ON (no model, ~40 s) =="
  # only pitch the custom-route form when the user hasn't already given one
  [ $# -ge 3 ] || echo "   (try your own route: $0 demo LAX ORD 2026-09-01)"
  case "$ON" in
    [0-9][0-9][0-9][0-9]-[0-9]*-[0-9]*) ;;
    *) echo "!! date must be YYYY-MM-DD (e.g. 2026-09-01), got: $ON" >&2; exit 1 ;;
  esac
  spec "$FROM" "$TO" "$ON"
  (cd "$WORK" && WORKSPACE_DIR="$WORK" python "$(ls -d "$LIB"/what_is_the_earliest_nonstop_flight_*)/skill.py" taskspec.json > run.log 2>&1) || { tail -5 "$WORK/run.log"; exit 1; }
  echo
  echo "-- what it did (no model chose these steps — they are the skill's code) --"
  sed -n 's/^\(step [0-9]*:\)/  \1/p' "$WORK"/runs/run_*/skill_log.txt 2>/dev/null || true
  echo
  echo "answer: $(cat "$WORK/agent_response.json")"
  SHOTS=$(ls "$WORK"/runs/run_*/screenshots/*.png 2>/dev/null | wc -l)
  echo "evidence: $SHOTS screenshots + step log ->"
  echo "  $(ls -d "$WORK"/runs/run_* 2>/dev/null | head -1)"
  echo "-> a learned skill just drove the live site with ZERO tokens. Next: $0 ask | solve"
  ;;
ask)
  need_key
  echo "== asking the library about a route it has never seen (one LLM round trip) =="
  python -m webwright.tools.skill_use \
    --task "$(flight_task 'Portland (PDX)' 'Austin (AUS)')" --library "$LIB"
  ;;
solve)
  need_key
  warn_gateway_agent
  echo "== one agent solve on an UNSEEN route, reusing the checked-in skill =="
  ./solve_with_library.sh "$(flight_task 'Portland (PDX)' 'Austin (AUS)')" \
    https://www.google.com/flights "$LIB" -o "$WORK/outputs" --task-id qs_solve "${CFG[@]}"
  echo "skill decision: $(cat "$WORK"/outputs/qs_solve_*/skill_decision.json 2>/dev/null || echo '(missing)')"
  echo "answer:         $(cat "$WORK"/outputs/qs_solve_*/agent_response.json 2>/dev/null || echo '(missing)')"
  ;;
*)
  # print the whole header comment — robust to edits, unlike a fixed line range
  awk 'NR>1 && /^#/ {print; next} NR>1 {exit}' "$SELF"; exit 1
  ;;
esac
echo "(work dir: $WORK)"

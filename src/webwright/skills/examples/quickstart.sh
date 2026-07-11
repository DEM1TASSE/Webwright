#!/usr/bin/env bash
# One-command Quickstart — every parameter pre-filled, nothing to write.
#
#   ./quickstart.sh          # instant: run the checked-in flights skill, NO model, no API key
#   ./quickstart.sh ask      # ask the library about a new task    (needs OPENAI_API_KEY)
#   ./quickstart.sh solve    # one agent solve that REUSES the checked-in skill (needs key)
#   ./quickstart.sh full     # the whole loop: 3 solves -> learn -> reuse (needs key, ~30 min)
#
# Custom / OpenAI-compatible gateway? Two knobs, both needed:
#   export OPENAI_ENDPOINT=... OPENAI_MODEL=...   (for learn / skill_use)
#   export MODEL_CFG=/path/to/your_model.yaml     (for the agent in solve/full — copy
#     model_openai.yaml and set openai_endpoint/model_name; env vars do NOT reach it)
set -euo pipefail
SELF="$(readlink -f "$0")"
cd "$(dirname "$SELF")"
DATE=$(date -d "+30 days" +%Y-%m-%d 2>/dev/null || date -v+30d +%Y-%m-%d)
WORK="${QUICKSTART_WORKDIR:-$(mktemp -d /tmp/skills_quickstart.XXXX)}"
LIB="$PWD/learned_library"
CFG=(-c base.yaml -c "${MODEL_CFG:-model_openai.yaml}")

need_key() { : "${OPENAI_API_KEY:?export OPENAI_API_KEY first (on a gateway also OPENAI_ENDPOINT / OPENAI_MODEL)}"; }

flight_task() { # $1 "City (CODE)"  $2 "City (CODE)"
  echo "What is the cheapest flight from $1 to $2 on $DATE (one-way)? Return the answer as a list: [airline, price]."
}

spec() { # $1 city $2 code $3 city $4 code -> taskspec.json in $WORK
  cat > "$WORK/taskspec.json" <<EOF
{"params": {"origin_city": "$1", "origin_code": "$2", "destination_city": "$3",
            "destination_code": "$4", "date": "$DATE"},
 "output_schema": {"type": "array", "items": {"type": "string"}}}
EOF
}

case "${1:-demo}" in
demo)
  echo "== the checked-in flights skill, standalone: cheapest SEA->DEN on $DATE (no model, ~30 s) =="
  spec Seattle SEA Denver DEN
  (cd "$WORK" && WORKSPACE_DIR="$WORK" python "$(ls -d "$LIB"/what_is_the_cheapest_flight_*)/skill.py" taskspec.json > run.log 2>&1) || { tail -5 "$WORK/run.log"; exit 1; }
  echo "answer: $(cat "$WORK/agent_response.json")"
  echo "-> a learned skill just drove the live site with ZERO tokens. Next: $0 ask | solve | full"
  ;;
ask)
  need_key
  echo "== asking the library about a route it has never seen (one LLM round trip) =="
  python -m webwright.tools.skill_use \
    --task "$(flight_task 'Portland (PDX)' 'Austin (AUS)')" --library "$LIB"
  ;;
solve)
  need_key
  echo "== one agent solve on an UNSEEN route, reusing the checked-in skill =="
  ./solve_with_library.sh "$(flight_task 'Portland (PDX)' 'Austin (AUS)')" \
    https://www.google.com/flights "$LIB" -o "$WORK/outputs" --task-id qs_solve "${CFG[@]}"
  echo "skill decision: $(cat "$WORK"/outputs/qs_solve_*/skill_decision.json 2>/dev/null || echo '(missing)')"
  echo "answer:         $(cat "$WORK"/outputs/qs_solve_*/agent_response.json 2>/dev/null || echo '(missing)')"
  ;;
full)
  need_key
  echo "== full loop: 3 from-scratch solves -> learn -> reuse on an unseen route (~30 min) =="
  for r in "Seattle (SEA)|New York (JFK)" "San Francisco (SFO)|Boston (BOS)" "Los Angeles (LAX)|Chicago (ORD)"; do
    FROM="${r%|*}"; TO="${r#*|}"
    echo "-- solving $FROM -> $TO from scratch"
    ./solve_with_library.sh "$(flight_task "$FROM" "$TO")" \
      https://www.google.com/flights "$WORK/library" -o "$WORK/outputs" "${CFG[@]}"
  done
  echo "-- learning (verify=shape: flight prices are live data — strict replay would
     compare against a price that may have moved since the solve)"
  python -m webwright.skills learn "$WORK/outputs" --library "$WORK/library" --verify shape
  echo "-- reusing on an unseen route"
  ./solve_with_library.sh "$(flight_task 'Seattle (SEA)' 'Denver (DEN)')" \
    https://www.google.com/flights "$WORK/library" -o "$WORK/outputs" --task-id qs_heldout "${CFG[@]}"
  echo "skill decision: $(cat "$WORK"/outputs/qs_heldout_*/skill_decision.json 2>/dev/null || echo '(missing)')"
  echo "library now at: $WORK/library"
  ;;
*)
  sed -n '2,10p' "$SELF"; exit 1
  ;;
esac
echo "(work dir: $WORK)"

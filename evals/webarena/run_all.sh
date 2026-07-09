#!/usr/bin/env bash
# Run the full WebArena reproduction sequentially (100 solves — hours of wall time
# and real model cost; see README.md; parallelize per template if you can).
#
#   export OPENAI_API_KEY=...            # + OPENAI_ENDPOINT / OPENAI_MODEL on a gateway
#   export WEBARENA_DATASET=/path/to/webarena-verified.json
#   export WEBARENA_CONFIG=/path/to/your/verified_config.json
#   ./run_all.sh [extra reproduce.py flags, e.g. --eval-python /path/to/python]
set -euo pipefail
cd "$(dirname "$0")"
[ -n "${WEBARENA_DATASET:-}" ] && [ -n "${WEBARENA_CONFIG:-}" ] || {
  echo "usage: set WEBARENA_DATASET and WEBARENA_CONFIG first (see README.md)" >&2; exit 1; }

python reproduce.py plan | grep '^python' | while read -r line; do
  echo "== $line"
  $line "$@"
done
python reproduce.py table "$@"

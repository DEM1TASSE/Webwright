#!/bin/bash
# Run the WebArena homepage for instance k (k=0 uses the repo copy).
K=${1:-0}
if [ "$K" = "0" ]; then
  D=/data/webarena/repo/environment_docker/webarena-homepage
else
  D=/data/webarena/homepage_$K
fi
cd "$D" || exit 1
exec python3.11 -m flask --app app run --host=0.0.0.0 --port=$((4399 + K*100))

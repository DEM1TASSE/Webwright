#!/usr/bin/env bash
# Bake the settings a WebArena GitLab needs into an image, so a rebuild cannot lose them.
#
# Three defaults break a benchmark run and all three live inside the container, which means a
# hand-applied fix disappears the next time the container is recreated -- that is how this was
# hit twice. external_url stays out: it differs per instance and the reset path sets it.
#
# --shm-size cannot be baked; it is a runtime flag and the reset path must still pass it.
set -euo pipefail
BASE=${BASE_IMAGE:-gitlab-populated-final-port8023}
OUT=${OUT_IMAGE:-gitlab-webarena-tuned}
TMP=gitlab_tuning_build_$$

cleanup() { docker rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "starting $TMP from $BASE"
docker run -d --name "$TMP" --shm-size=2g "$BASE" /opt/gitlab/embedded/bin/runsvdir-start >/dev/null
sleep 90

docker exec "$TMP" bash -c 'grep -q WEBARENA_TUNING /etc/gitlab/gitlab.rb || cat >> /etc/gitlab/gitlab.rb <<RB

# WEBARENA_TUNING
# Puma defaults to one worker per core and preloads Rails into each; on a many-core host it
# never finishes booting and every request 502s while the container reports healthy.
puma["worker_processes"] = 24
puma["min_threads"] = 4
puma["max_threads"] = 8
sidekiq["max_concurrency"] = 10
# Metrics are written into /dev/shm on every request; with the container default of 64M it
# fills and each later request fails with IOError(unmapped file), independent of load.
prometheus_monitoring["enable"] = false
# 200 is exhausted by roughly a dozen concurrent agents.
postgresql["max_connections"] = 600
RB'

echo "reconfiguring"
docker exec "$TMP" gitlab-ctl reconfigure >/dev/null
docker exec "$TMP" gitlab-ctl stop >/dev/null

echo "committing $OUT"
docker commit --change 'CMD ["/opt/gitlab/embedded/bin/runsvdir-start"]' "$TMP" "$OUT" >/dev/null
docker images "$OUT" --format '  built {{.Repository}}:{{.Tag}} {{.Size}}'

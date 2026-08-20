#!/usr/bin/env bash
# Bake a self-hosted WebArena GitLab's required settings into an image.
#
# Three container defaults make a fraction of requests 5xx under a benchmark run, and the
# resulting tasks score zero in a way that reads as a weak agent. All three live inside the
# container, so a hand-applied fix disappears the next time it is recreated — which is how
# they were hit repeatedly here, including once by bypassing the reset script and running
# docker run directly. Applying them at image level removes the dependency on remembering.
#
#   usage:  build_tuned_gitlab_image.sh [base-image] [output-image]
#
# Run once per deployment; recreate containers from the output image afterwards. Verify with
# gitlab_deployment_fixup.sh, which samples the site rather than trusting a single 200.
set -euo pipefail
BASE=${1:-gitlab-populated-final-port8023}
OUT=${2:-gitlab-webarena-tuned}
TMP="gitlab_tuning_build_$$"

cleanup() { docker rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# --shm-size is a runtime flag and cannot be baked, so whatever creates the real containers
# must still pass it. It is set here only so the build itself does not hit the same wall.
docker run -d --name "$TMP" --shm-size=2g "$BASE" /opt/gitlab/embedded/bin/runsvdir-start >/dev/null
sleep 90

docker exec "$TMP" bash -c 'grep -q WEBARENA_TUNING /etc/gitlab/gitlab.rb || cat >> /etc/gitlab/gitlab.rb <<RB

# WEBARENA_TUNING
# Puma defaults to one worker per core and preloads Rails into each. On a many-core host it
# never finishes booting, is killed, and restarts forever: nginx has nothing to reach, so every
# request is a 502 while docker ps still reports the container healthy.
puma["worker_processes"] = 24
puma["min_threads"] = 4
puma["max_threads"] = 8
sidekiq["max_concurrency"] = 10
# Metrics are written into /dev/shm on every request. At the 64M container default it fills,
# and from then on every request fails with IOError(unmapped file), independent of load.
prometheus_monitoring["enable"] = false
# 200 is exhausted by roughly a dozen concurrent agents; the rest get
# ActiveRecord::ConnectionNotEstablished.
postgresql["max_connections"] = 600
RB'

docker exec "$TMP" gitlab-ctl reconfigure >/dev/null
docker exec "$TMP" gitlab-ctl stop >/dev/null

# external_url is deliberately not baked: it differs per instance and belongs to whatever
# creates the container.
docker commit --change 'CMD ["/opt/gitlab/embedded/bin/runsvdir-start"]' "$TMP" "$OUT" >/dev/null
docker images "$OUT" --format 'built {{.Repository}}:{{.Tag}} {{.Size}}'

#!/usr/bin/env bash
# Settings a self-hosted WebArena GitLab needs before it can serve a benchmark run.
#
# Without them a fraction of requests answer 5xx and the tasks that hit them score zero in a
# way that reads as a weak agent, not as broken infrastructure. Both defaults were found by
# probing the site at zero load; concurrency was wrongly blamed twice first.
#
#   usage:  gitlab_deployment_fixup.sh <container> <external-url>
#   e.g.    gitlab_deployment_fixup.sh gitlab_2 http://host.example.com:8223
#
# --shm-size cannot be applied to an existing container, so this script reports it rather than
# fixing it: whatever creates the container has to pass it.
set -euo pipefail
container=${1:?container name}
external_url=${2:?external url}

shm=$(docker exec "$container" df -m /dev/shm | awk 'NR==2 {print $2}')
if [ "${shm:-0}" -lt 512 ]; then
  echo "FAIL: /dev/shm is ${shm}M. GitLab writes Prometheus metrics there on every request;" >&2
  echo "      once full, every request 500s with IOError(unmapped file) regardless of load." >&2
  echo "      Recreate the container with --shm-size=2g -- it cannot be changed in place." >&2
  exit 1
fi

# Everything below lives inside the container, so a rebuild drops all of it. Rewrite each
# time rather than fixing by hand once.
docker exec "$container" bash -c "
  sed -i \"s|^external_url.*|external_url '${external_url}'|\" /etc/gitlab/gitlab.rb
  grep -q \"^postgresql\['max_connections'\]\" /etc/gitlab/gitlab.rb ||
    echo \"postgresql['max_connections'] = 600\" >> /etc/gitlab/gitlab.rb
  # Puma defaults to one worker per core and preloads Rails into each. On a many-core host it
  # never finishes booting, gets killed, and restarts forever, so nginx has nothing to reach
  # and every request is a 502 while the container still reports healthy.
  grep -q \"^puma\['worker_processes'\]\" /etc/gitlab/gitlab.rb ||
    printf \"%s\\n\" \"puma['worker_processes'] = 24\" \"puma['min_threads'] = 4\" \
      \"puma['max_threads'] = 8\" \"sidekiq['max_concurrency'] = 10\" >> /etc/gitlab/gitlab.rb
"
docker exec "$container" gitlab-ctl reconfigure >/dev/null
# reconfigure rewrites postgresql.conf but leaves the running server on the old value.
docker exec "$container" gitlab-ctl restart postgresql >/dev/null
sleep 15
docker exec "$container" gitlab-ctl restart puma >/dev/null
docker exec "$container" gitlab-ctl restart sidekiq >/dev/null

deadline=$(( $(date +%s) + 600 ))
until [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${external_url}/explore")" = "200" ]; do
  [ "$(date +%s)" -gt "$deadline" ] && { echo "FAIL: not serving 200 after 10 minutes" >&2; exit 1; }
  sleep 10
done

# A single 200 proves little: the failure mode is intermittent. Sample before trusting it.
codes=$(for _ in $(seq 20); do
  curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "${external_url}/explore"
done | sort | uniq -c | tr '\n' ' ')
echo "shm=${shm}M max_connections=$(docker exec "$container" gitlab-psql -tAc 'SHOW max_connections;' 2>/dev/null)"
echo "20-sample probe: ${codes}"
case "$codes" in *" 200 "*) [ "${codes// /}" = "20200" ] || echo "WARNING: not all 200 -- do not trust a batch against this site" >&2 ;; esac

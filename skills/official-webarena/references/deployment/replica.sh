#!/bin/bash
# Launch / remove additional parallel WebArena instances.
# Instance k (k>=1) uses ports offset by k*100:
#   shopping 7770+k*100, shopping_admin 7780+k*100, forum 9999+k*100,
#   gitlab 8023+k*100, wikipedia 8888+k*100, homepage 4399+k*100
# Containers are named <site>_k. Images are shared, so extra disk use is small.
HOST=${WA_HOST:-GCRSANDBOX410.redmond.corp.microsoft.com}
K=$2
[ -z "$K" ] && { echo "usage: $0 {up|down|reset|status|urls} <instance-number>"; exit 1; }
OFF=$((K*100))
SHOP=$((7770+OFF)); ADMIN=$((7780+OFF)); FORUM=$((9999+OFF)); GITLAB=$((8023+OFF))
WIKI=$((8888+OFF)); HOME_P=$((4399+OFF))
TARS=/data/webarena/tars
HOMEPAGE_SRC=/data/webarena/repo/environment_docker/webarena-homepage

case "$1" in
up)
  # Preflight: a mid-way port clash used to leave a half-created instance behind
  # (set -e aborts after the first containers are already running). The map stack
  # sits outside the +100 grid on purpose -- tile was moved off 8080 because
  # 7780+300 lands on it, which broke instance 3.
  busy=""
  for p in $SHOP $ADMIN $FORUM $GITLAB $WIKI $HOME_P; do
    ss -tln | grep -q ":$p " && busy="$busy $p"
  done
  if [ -n "$busy" ]; then
    echo "refusing to start instance $K: port(s) already in use:$busy"
    exit 1
  fi
  for c in shopping_$K shopping_admin_$K forum_$K gitlab_$K wikipedia_$K; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
      echo "refusing to start instance $K: container $c already exists (use 'down $K' first)"
      exit 1
    fi
  done
  set -e
  docker run --network webarena --name shopping_$K       -p $SHOP:80  -d shopping_final_0712
  docker run --network webarena --name shopping_admin_$K -p $ADMIN:80 -d shopping_admin_final_0719
  docker run --network webarena --name forum_$K          -p $FORUM:80 -d postmill-populated-exposed-withimg
  # --shm-size must be set at creation: GitLab writes Prometheus metrics into /dev/shm on every
  # request, the 64M default fills up, and from then on every request 500s with
  # IOError(unmapped file) regardless of load.
  docker run --network webarena --name gitlab_$K -d --shm-size=2g -p $GITLAB:$GITLAB gitlab-webarena-tuned /opt/gitlab/embedded/bin/runsvdir-start
  docker run --network webarena --name wikipedia_$K --volume=$TARS/:/data -p $WIKI:80 -d \
    ghcr.io/kiwix/kiwix-serve:3.3.0 wikipedia_en_all_maxi_2022-05.zim
  set +e
  echo "containers up; waiting 5 min for boot before configuring"
  sleep 300
  docker exec shopping_$K /var/www/magento2/bin/magento setup:store-config:set --base-url="http://$HOST:$SHOP"
  docker exec shopping_$K mysql -u magentouser -pMyPassword magentodb \
    -e "UPDATE core_config_data SET value=\"http://$HOST:$SHOP/\" WHERE path = \"web/secure/base_url\";"
  docker exec shopping_$K /var/www/magento2/bin/magento cache:flush
  docker exec shopping_admin_$K /var/www/magento2/bin/magento setup:store-config:set --base-url="http://$HOST:$ADMIN"
  docker exec shopping_admin_$K mysql -u magentouser -pMyPassword magentodb \
    -e "UPDATE core_config_data SET value=\"http://$HOST:$ADMIN/\" WHERE path = \"web/secure/base_url\";"
  docker exec shopping_admin_$K php /var/www/magento2/bin/magento config:set admin/security/password_is_forced 0
  docker exec shopping_admin_$K php /var/www/magento2/bin/magento config:set admin/security/password_lifetime 0
  # Magento redirects to its stored base_url on ANY host mismatch, and Chromium reports a
  # lowercased host. The result is an endless 302 loop that no login can survive. Turning the
  # redirect off is what breaks it; matching the case is not enough, because the loop also
  # fires for localhost and for the tunnelled host.
  for c in shopping_$K shopping_admin_$K; do
    docker exec $c php /var/www/magento2/bin/magento config:set web/url/redirect_to_base 0
    docker exec $c /var/www/magento2/bin/magento cache:flush
  done
  docker exec gitlab_$K sed -i "s|^external_url.*|external_url 'http://$HOST:$GITLAB'|" /etc/gitlab/gitlab.rb
  # 128-core host: GitLab sizes puma by CPU count (128 workers) and then trips
  # prometheus-client-mmap's "IOError (unmapped file)" -> intermittent 500/502.
  docker exec gitlab_$K bash -c 'grep -q "WEBARENA_TUNING" /etc/gitlab/gitlab.rb || cat >> /etc/gitlab/gitlab.rb <<EOF

# WEBARENA_TUNING
puma["worker_processes"] = 24
puma["min_threads"] = 4
puma["max_threads"] = 8
sidekiq["max_concurrency"] = 10
prometheus_monitoring["enable"] = false
EOF'
  docker exec gitlab_$K gitlab-ctl reconfigure
  # per-instance homepage
  D=/data/webarena/homepage_$K
  rm -rf "$D"; cp -r "$HOMEPAGE_SRC" "$D"
  sed -i "s|:7770|:$SHOP|g;s|:7780|:$ADMIN|g;s|:9999|:$FORUM|g;s|:8023|:$GITLAB|g;s|:8888|:$WIKI|g" "$D/templates/index.html"
  (cd "$D" && nohup python3.11 -m flask run --host=0.0.0.0 --port=$HOME_P > /data/webarena/homepage_$K.log 2>&1 &)
  python3.11 /data/webarena/gen_instances.py
  echo "instance $K ready"
  $0 urls $K
  ;;
down)
  docker rm -f shopping_$K shopping_admin_$K forum_$K gitlab_$K wikipedia_$K 2>/dev/null
  pkill -f "flask.*--port=$HOME_P"   # the command line carries --app between flask and run
  rm -rf /data/webarena/homepage_$K
  python3.11 /data/webarena/gen_instances.py
  echo "instance $K removed"
  ;;
reset)
  # Reset a replica to pristine state: the data lives only in the container's
  # writable layer, so destroying and recreating it is the reset.
  "$0" down "$K"
  "$0" up "$K"
  ;;
status)
  docker ps -a --format "{{.Names}}\t{{.Status}}" | grep -E "_$K\b"
  ;;
urls)
  echo "SHOPPING=http://$HOST:$SHOP"
  echo "SHOPPING_ADMIN=http://$HOST:$ADMIN/admin"
  echo "REDDIT=http://$HOST:$FORUM"
  echo "GITLAB=http://$HOST:$GITLAB"
  echo "WIKIPEDIA=http://$HOST:$WIKI/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
  echo "HOMEPAGE=http://$HOST:$HOME_P"
  ;;
*) echo "usage: $0 {up|down|reset|status|urls} <instance-number>"; exit 1;;
esac

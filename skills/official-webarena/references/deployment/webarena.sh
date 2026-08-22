#!/bin/bash
# WebArena environment manager on GCRSANDBOX410
# Usage: webarena.sh {status|start|stop|reset|configure|homepage}
# lowercase: Chromium lowercases hostnames; an uppercase Magento base_url causes ERR_TOO_MANY_REDIRECTS
HOST=${WA_HOST:-gcrsandbox410.redmond.corp.microsoft.com}
HOMEPAGE_DIR=/data/webarena/repo/environment_docker/webarena-homepage
TARS=/data/webarena/tars

configure_shopping(){
  docker exec shopping /var/www/magento2/bin/magento setup:store-config:set --base-url="http://$HOST:7770"
  docker exec shopping mysql -u magentouser -pMyPassword magentodb \
    -e "UPDATE core_config_data SET value=\"http://$HOST:7770/\" WHERE path = \"web/secure/base_url\";"
  docker exec shopping /var/www/magento2/bin/magento cache:flush
}
configure_shopping_admin(){
  docker exec shopping_admin /var/www/magento2/bin/magento setup:store-config:set --base-url="http://$HOST:7780"
  docker exec shopping_admin mysql -u magentouser -pMyPassword magentodb \
    -e "UPDATE core_config_data SET value=\"http://$HOST:7780/\" WHERE path = \"web/secure/base_url\";"
  docker exec shopping_admin php /var/www/magento2/bin/magento config:set admin/security/password_is_forced 0
  docker exec shopping_admin php /var/www/magento2/bin/magento config:set admin/security/password_lifetime 0
  docker exec shopping_admin /var/www/magento2/bin/magento cache:flush
}
configure_gitlab(){
  docker exec gitlab sed -i "s|^external_url.*|external_url 'http://$HOST:8023'|" /etc/gitlab/gitlab.rb
  # 128-core host: GitLab sizes puma by CPU count (128 workers) and then trips
  # prometheus-client-mmap's "IOError (unmapped file)" -> intermittent 500/502.
  docker exec gitlab bash -c 'grep -q "WEBARENA_TUNING" /etc/gitlab/gitlab.rb || cat >> /etc/gitlab/gitlab.rb <<EOF

# WEBARENA_TUNING
puma["worker_processes"] = 24
puma["min_threads"] = 4
puma["max_threads"] = 8
sidekiq["max_concurrency"] = 10
prometheus_monitoring["enable"] = false
EOF'
  docker exec gitlab gitlab-ctl reconfigure
}

case "$1" in
  status)
    docker ps -a --filter name=shopping --filter name=shopping_admin --filter name=forum \
      --filter name=gitlab --filter name=wikipedia --filter name=tile --filter name=nominatim \
      --filter name=osrm --filter name=openstreetmap --format "{{.Names}}\t{{.Status}}"
    echo "---- HTTP checks ----"
    for e in "OneStopShop 7770 /" "CMS 7780 /admin" "Reddit 9999 /forums/all" \
             "GitLab 8023 /explore" "Wikipedia 8888 /" "Homepage 4399 /" \
             "Map 3000 /" "MapTile 8080 /tile/0/0/0.png" "Geocode 8085 /status" \
             "OSRMcar 5000 /route/v1/driving/-79.94,40.44;-79.99,40.44?overview=false"; do
      set -- $e
      printf "%-12s %-5s " "$1" "$2"
      curl -s -o /dev/null -m 20 -w "%{http_code}\n" "http://$HOST:$2$3"
    done
    ;;
  start)
    docker start shopping shopping_admin forum gitlab wikipedia 2>/dev/null
    echo "waiting 60s for services"; sleep 60
    ;;
  stop)
    docker stop shopping shopping_admin forum gitlab wikipedia 2>/dev/null
    ;;
  configure)
    configure_shopping; configure_shopping_admin; configure_gitlab
    ;;
  reset)
    # full reset to pristine state (per WebArena README)
    docker stop shopping shopping_admin forum gitlab 2>/dev/null
    docker rm   shopping shopping_admin forum gitlab 2>/dev/null
    # --restart is re-applied here: recreating the containers drops the policy
    # that was set on the previous ones, which would silently break auto-start
    # after a host reboot.
    docker run --restart unless-stopped --name shopping       -p 7770:80 -d shopping_final_0712
    docker run --restart unless-stopped --name shopping_admin -p 7780:80 -d shopping_admin_final_0719
    docker run --restart unless-stopped --name forum          -p 9999:80 -d postmill-populated-exposed-withimg
    # see replica.sh: /dev/shm default of 64M fills with Prometheus metrics and every
    # subsequent request 500s with IOError(unmapped file)
    docker run --restart unless-stopped --name gitlab -d --shm-size=2g -p 8023:8023 gitlab-webarena-tuned /opt/gitlab/embedded/bin/runsvdir-start
    echo "waiting 5 min for boot"; sleep 300
    configure_shopping; configure_shopping_admin; configure_gitlab
    ;;
  homepage)
    # managed by systemd (webarena-homepage@0); restarting by hand would fight the unit
    sudo systemctl restart webarena-homepage@0
    systemctl is-active webarena-homepage@0
    ;;
  *) echo "usage: $0 {status|start|stop|reset|configure|homepage}"; exit 1;;
esac

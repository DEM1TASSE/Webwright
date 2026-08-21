#!/bin/bash
# Sequentially load + run + configure remaining WebArena sites
HOST=GCRSANDBOX410.redmond.corp.microsoft.com
DIR=/data/webarena/tars
LOG=/data/webarena/setup.log
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

wait_for_download(){  # $1=filename $2=expected size
  while true; do
    if [ -f "$DIR/$1" ] && [ "$(stat -c %s "$DIR/$1")" = "$2" ]; then return 0; fi
    sleep 60
  done
}

# ---------- 1. forum (postmill) : image already loading in background ----------
log "waiting for postmill image to finish loading"
while ! docker image inspect postmill-populated-exposed-withimg >/dev/null 2>&1; do sleep 30; done
if ! docker ps -a --format '{{.Names}}' | grep -qx forum; then
  docker run --name forum -p 9999:80 -d postmill-populated-exposed-withimg >> "$LOG" 2>&1
  log "forum started on 9999"
fi

# ---------- 2. shopping ----------
wait_for_download shopping_final_0712.tar 67575898112
log "loading shopping image"
docker load --input "$DIR/shopping_final_0712.tar" >> "$LOG" 2>&1
docker run --name shopping -p 7770:80 -d shopping_final_0712 >> "$LOG" 2>&1
log "shopping container started, waiting 90s"
sleep 90
docker exec shopping /var/www/magento2/bin/magento setup:store-config:set --base-url="http://$HOST:7770" >> "$LOG" 2>&1
docker exec shopping mysql -u magentouser -pMyPassword magentodb -e "UPDATE core_config_data SET value=\"http://$HOST:7770/\" WHERE path = \"web/secure/base_url\";" >> "$LOG" 2>&1
docker exec shopping /var/www/magento2/bin/magento cache:flush >> "$LOG" 2>&1
log "shopping configured: http://$HOST:7770"

# ---------- 3. gitlab ----------
wait_for_download gitlab-populated-final-port8023.tar 77755595776
log "loading gitlab image"
docker load --input "$DIR/gitlab-populated-final-port8023.tar" >> "$LOG" 2>&1
docker run --name gitlab -d -p 8023:8023 gitlab-populated-final-port8023 /opt/gitlab/embedded/bin/runsvdir-start >> "$LOG" 2>&1
log "gitlab container started, waiting 5 min for boot"
sleep 300
docker exec gitlab sed -i "s|^external_url.*|external_url 'http://$HOST:8023'|" /etc/gitlab/gitlab.rb >> "$LOG" 2>&1
docker exec gitlab gitlab-ctl reconfigure >> "$LOG" 2>&1
log "gitlab reconfigured: http://$HOST:8023"

# ---------- 4. wikipedia (kiwix) ----------
wait_for_download wikipedia_en_all_maxi_2022-05.zim 95199730590
log "starting kiwix"
docker run -d --name wikipedia --volume=$DIR/:/data -p 8888:80 \
  ghcr.io/kiwix/kiwix-serve:3.3.0 wikipedia_en_all_maxi_2022-05.zim >> "$LOG" 2>&1
log "kiwix started: http://$HOST:8888"

log "ALL SITES SETUP COMPLETE"

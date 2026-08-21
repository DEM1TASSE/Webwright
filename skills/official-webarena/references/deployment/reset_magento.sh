#!/bin/bash
# 重建一个 Magento 站点容器并补齐 reset 后必需的配置。
# 镜像里烤的是 CMU 原始 base_url，不修的话本地全是 302；
# redirect_to_base=0 是本部署的额外修复（host 大小写/别名不匹配会 302 死循环）。
set -u
K=${2:-2}; HOST=GCRSANDBOX410.redmond.corp.microsoft.com
case "$1" in
  shopping)       NAME=shopping_$K;       IMAGE=shopping_final_0712;       PORT=$((7770+K*100)); BASE="http://$HOST:$PORT" ; PROBE=/ ;;
  shopping_admin) NAME=shopping_admin_$K; IMAGE=shopping_admin_final_0719; PORT=$((7780+K*100)); BASE="http://$HOST:$PORT" ; PROBE=/admin ;;
  *) echo "usage: $0 {shopping|shopping_admin} [instance]"; exit 1;;
esac
S=$(date +%s)
docker rm -f "$NAME" >/dev/null 2>&1
docker run --network webarena --name "$NAME" --restart unless-stopped -p "$PORT":80 -d "$IMAGE" >/dev/null
until docker exec "$NAME" mysqladmin -u magentouser -pMyPassword ping >/dev/null 2>&1; do
  sleep 3; [ $(( $(date +%s)-S )) -gt 400 ] && { echo "$NAME: mysql 未就绪"; exit 1; }
done
M=/var/www/magento2/bin/magento
docker exec "$NAME" $M setup:store-config:set --base-url="$BASE" >/dev/null 2>&1
docker exec "$NAME" mysql -u magentouser -pMyPassword magentodb \
  -e "UPDATE core_config_data SET value='$BASE/' WHERE path='web/secure/base_url';
      INSERT INTO core_config_data (scope,scope_id,path,value) VALUES ('default',0,'web/url/redirect_to_base','0')
      ON DUPLICATE KEY UPDATE value='0';" >/dev/null 2>&1
if [ "$1" = "shopping_admin" ]; then
  docker exec "$NAME" php $M config:set admin/security/password_is_forced 0 >/dev/null 2>&1
  docker exec "$NAME" php $M config:set admin/security/password_lifetime 0 >/dev/null 2>&1
fi
docker exec "$NAME" $M cache:flush >/dev/null 2>&1
until [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$PORT$PROBE")" = "200" ]; do
  sleep 3; [ $(( $(date +%s)-S )) -gt 600 ] && { echo "$NAME: HTTP 未就绪"; exit 1; }
done
echo "$NAME reset+fixup 完成: $(( $(date +%s)-S ))s"

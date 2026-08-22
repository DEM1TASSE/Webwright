#!/bin/bash
# Deploy the WebArena map backend on 410: tile server, Nominatim, OSRM x3.
#
# Data comes from the official public S3 bucket (which lives in us-east-1, not
# us-east-2 as the docs imply). The strip-components values differ from the
# official cloud-init: the tarballs we got are nested one level shallower for
# the tile data and one level deeper for osm_dump than that script assumes.
set -eu
TARS=/data/webarena/map
VOLS=/data/docker/volumes          # docker data-root on this host is /data/docker
OSM_DUMP=/data/webarena/map/osm_dump
OSRM=/data/webarena/map/osrm
LOG=/data/webarena/map_backend.log

log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "creating volumes"
for v in osm-data osm-tiles nominatim-data nominatim-flatnode; do
  docker volume create "$v" >/dev/null
done

if [ ! -f "$VOLS/osm-data/_data/planet-import-complete" ]; then
  log "extracting tile data (41GB)"
  sudo tar -C "$VOLS" --strip-components=4 -xf "$TARS/osm_tile_server.tar"
fi

if [ ! -d "$VOLS/nominatim-data/_data/base" ]; then
  log "extracting nominatim data (125GB)"
  sudo tar -C "$VOLS" --strip-components=5 -xf "$TARS/nominatim_volumes.tar"
fi

if [ ! -f "$OSM_DUMP/us-northeast-latest.osm.pbf" ]; then
  log "extracting osm dump"
  mkdir -p "$OSM_DUMP"
  tar -C "$OSM_DUMP" --strip-components=1 -xf "$TARS/osm_dump.tar"
fi

if [ ! -d "$OSRM/car" ]; then
  log "extracting osrm routing data (21GB)"
  mkdir -p "$OSRM"
  tar -C "$OSRM" -xf "$TARS/osrm_routing.tar"
fi

log "starting tile server on 6080"
docker rm -f tile >/dev/null 2>&1 || true
docker run --name tile --restart unless-stopped \
  --volume=osm-data:/data/database/ --volume=osm-tiles:/data/tiles/ \
  -p 6080:80 -d overv/openstreetmap-tile-server run >/dev/null

log "starting nominatim on 8085"
docker rm -f nominatim >/dev/null 2>&1 || true
docker run --name nominatim --restart unless-stopped \
  --env=IMPORT_STYLE=extratags \
  --env=PBF_PATH=/nominatim/data/us-northeast-latest.osm.pbf \
  --env=IMPORT_WIKIPEDIA=/nominatim/data/wikimedia-importance.sql.gz \
  --volume="$OSM_DUMP":/nominatim/data \
  --volume=nominatim-data:/var/lib/postgresql/14/main \
  --volume=nominatim-flatnode:/nominatim/flatnode \
  -p 8085:8080 -d mediagis/nominatim:4.2 /app/start.sh >/dev/null

for prof in car:5000 bike:5001 foot:5002; do
  name=${prof%%:*}; port=${prof##*:}
  log "starting osrm-$name on $port"
  docker rm -f "osrm-$name" >/dev/null 2>&1 || true
  docker run --name "osrm-$name" --restart unless-stopped \
    --volume="$OSRM/$name":/data -p "$port":5000 -d \
    ghcr.io/project-osrm/osrm-backend:v5.27.1 \
    osrm-routed --algorithm mld /data/us-northeast-latest.osrm >/dev/null
done

log "all backend containers started"

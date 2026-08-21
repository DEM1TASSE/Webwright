#!/bin/bash
# Bring up the WebArena map frontend (openstreetmap-website) on port 3000.
#
# Images and source came from the official AMI, so this is the same frontend
# WebArena's map tasks were written against -- not a rebuild from upstream.
# The 142GB Postgres dir is bind-mounted rather than copied into a named
# volume, which saves a second full write of it onto the RAID.
set -eu
DIR=/data/webarena/map_frontend/openstreetmap-website
DBDATA=/data/webarena/map_frontend/dbdata
PORT=${1:-3000}

[ -f "$DBDATA/PG_VERSION" ] || { echo "db data not ready at $DBDATA"; exit 1; }

# The container's postgres runs as uid 999; the tar carried the AMI's uids.
OWNER=$(docker run --rm --entrypoint id openstreetmap-website-db:latest -u postgres 2>/dev/null || echo 999)
echo "chowning db dir to uid $OWNER (this takes a minute on 142GB of files)"
sudo chown -R "$OWNER:$OWNER" "$DBDATA"
sudo chmod 700 "$DBDATA"

cat > "$DIR/docker-compose.override.yml" <<EOF
# Local overrides: bind-mount the AMI's Postgres data and pin the published port.
services:
  web:
    ports:
      - "$PORT:3000"
  db:
    volumes:
      - $DBDATA:/var/lib/postgresql/data
EOF

cd "$DIR"
docker compose up -d --no-build
echo "started; waiting for rails to boot"
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -m 10 -w "%{http_code}" "http://localhost:$PORT/" || true)
  [ "$code" = "200" ] && { echo "map frontend up on $PORT"; exit 0; }
  sleep 10
done
echo "still not answering 200 after 10 min; check: docker compose logs web"
exit 1

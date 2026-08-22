#!/bin/bash
# Pull the AMI's openstreetmap-website Postgres volume (142GB) to 410.
#
# The EC2 is a credit-exhausted t2.2xlarge (46% steal), so compressing on that
# side was slower than sending raw bytes. Parallel shards recover the loss:
# 1 stream = 9 MB/s, 4 streams = 34 MB/s. Six shards, no compression.
# Each shard keeps its own stderr file -- a failing ssh otherwise only shows up
# as local tar complaining that the (empty) stream is not an archive.
set -u
KEY=/home/t-demiwang/demi-webarena.pem
REMOTE=ubuntu@18.223.172.69
SSH="ssh -i $KEY -o BatchMode=yes -c aes128-gcm@openssh.com -o ServerAliveInterval=30 -o ServerAliveCountMax=6 $REMOTE"
DEST=/data/webarena/map_frontend/dbdata
LOG=/data/webarena/dl_mapdb.log
ERRDIR=/data/webarena/mapdb_err
SHARDS=6

log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
mkdir -p "$DEST" "$ERRDIR"

log "START db-data transfer ($SHARDS shards)"

# Everything except the big database dir: config files, WAL, global catalogs.
$SSH "sudo -n sh -c 'cd /var/lib/docker/volumes/openstreetmap-website_db-data/_data && tar -cf - --exclude=base/16384 .'" \
  2>"$ERRDIR/meta.err" | tar -xf - -C "$DEST" 2>>"$ERRDIR/meta.err"
log "metadata + WAL done ($(du -sh "$DEST" 2>/dev/null | cut -f1))"

# The 141GB database dir, sharded by file across parallel streams.
# Staggered so a loaded sshd does not see six handshakes at once.
for i in $(seq 0 $((SHARDS-1))); do
  (
    $SSH "sudo -n sh /tmp/part_tar.sh $i $SHARDS" 2>"$ERRDIR/shard$i.err" \
      | tar -xf - -C "$DEST" 2>>"$ERRDIR/shard$i.err"
    log "shard $i finished (stderr $(stat -c %s "$ERRDIR/shard$i.err") bytes)"
  ) &
  sleep 3
done
wait

log "ALL SHARDS DONE, local size $(du -sh "$DEST" 2>/dev/null | cut -f1)"

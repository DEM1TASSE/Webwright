#!/bin/bash
# Parallel-chunk downloader for WebArena images (resumable)
DIR=/data/webarena/tars
BASE=http://metis.lti.cs.cmu.edu/webarena-images
LOG=/data/webarena/dl.log
mkdir -p "$DIR"

log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

dl(){
  f=$1; n=${2:-8}
  size=$(curl -sI "$BASE/$f" | grep -i '^content-length' | tr -d '\r' | awk '{print $2}')
  [ -z "$size" ] && { log "FAIL: no size for $f"; return 1; }
  if [ -f "$DIR/$f" ] && [ "$(stat -c %s "$DIR/$f")" = "$size" ]; then
    log "SKIP $f (already complete, $size bytes)"; return 0
  fi
  log "START $f ($size bytes, $n chunks)"
  chunk=$(( (size + n - 1) / n ))
  for i in $(seq 0 $((n-1))); do
    s=$((i*chunk)); e=$((s+chunk-1)); [ $e -ge $size ] && e=$((size-1))
    [ $s -gt $e ] && continue
    (
      part="$DIR/$f.part$i"
      have=0; [ -f "$part" ] && have=$(stat -c %s "$part")
      want=$((e-s+1))
      while [ "$have" -lt "$want" ]; do
        curl -s --retry 5 --retry-delay 5 -r $((s+have))-$e "$BASE/$f" >> "$part"
        nh=$(stat -c %s "$part")
        [ "$nh" = "$have" ] && { sleep 10; }
        have=$nh
      done
    ) &
  done
  wait
  log "MERGE $f"
  cat $(for i in $(seq 0 $((n-1))); do [ -f "$DIR/$f.part$i" ] && echo "$DIR/$f.part$i"; done) > "$DIR/$f"
  got=$(stat -c %s "$DIR/$f")
  if [ "$got" = "$size" ]; then
    rm -f "$DIR/$f".part*
    log "DONE $f ($got bytes)"
  else
    log "SIZE MISMATCH $f: got $got want $size"
  fi
}

for spec in "shopping_admin_final_0719.tar 8" \
            "postmill-populated-exposed-withimg.tar 12" \
            "shopping_final_0712.tar 12" \
            "gitlab-populated-final-port8023.tar 12" \
            "wikipedia_en_all_maxi_2022-05.zim 12"; do
  dl $spec
done
log "ALL DOWNLOADS FINISHED"

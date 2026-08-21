#!/bin/bash
# Reverse tunnel: GCRSANDBOX410 -> GCRAZGDL1704 (10.8.162.118 / 72.154.168.97)
# 410 can reach the Azure VM but not vice versa, so the tunnel is initiated here.
# On the remote side each port binds to 127.0.0.1:<same port>, so the WebArena
# FQDN keeps working there via a hosts entry pointing at 127.0.0.1.
REMOTE_USER=${1:?usage: tunnel.sh <remote-user> [instance-k]}
K=${2:-0}
HOST=72.154.168.97
KEY=~/.ssh/webarena_tunnel
OFF=$((K*100))
# Forwards are "remotePort:localPort" pairs. Same-numbered by default, because
# Magento/GitLab 302 to the FQDN and the map JS hardcodes absolute backend URLs,
# so the remote side must answer on the same port for those to resolve.
PAIRS=""
for p in $((7770+OFF)) $((7780+OFF)) $((9999+OFF)) $((8023+OFF)) $((8888+OFF)) $((4399+OFF)); do
  PAIRS="$PAIRS $p:$p"
done
# Instance 0 also carries the map stack (only one copy exists; replicas share it).
# GCRAZGDL1704 already runs something on 3000, so the frontend lands on 13000
# there; the backend ports must stay same-numbered (they are baked into the JS).
[ "$K" = "0" ] && PAIRS="$PAIRS 13000:3000 6080:6080 8085:8085 5000:5000 5001:5001 5002:5002"

FWD=""
for pair in $PAIRS; do
  FWD="$FWD -R 127.0.0.1:${pair%%:*}:127.0.0.1:${pair##*:}"
done

echo "tunneling$PAIRS to $REMOTE_USER@$HOST"
while true; do
  ssh -N -i "$KEY" \
      -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -o StrictHostKeyChecking=accept-new \
      $FWD -l "$REMOTE_USER" "$HOST"
  echo "[$(date '+%F %T')] tunnel dropped, reconnecting in 10s"
  sleep 10
done

#!/bin/bash
# measure.sh <label> — measure WAN download / upload from this device with curl, while pinging
# 1.1.1.1 at the same time (ICMP passes through the shaper). If the cap works, curl sticks to the
# cap and ping does not spike. Output: one TSV line (stdout) and ping stats (stderr)
#
#   DOWN_BYTES / UP_BYTES set the transfer size (at a 1 Mbit/s cap, 1MB ≈ 8 s)
set -eu
LABEL=${1:-run}
DOWN_BYTES=${DOWN_BYTES:-2000000}
UP_BYTES=${UP_BYTES:-1000000}
tmp=$(mktemp -d)
head -c "$UP_BYTES" /dev/urandom >"$tmp/up.bin"

# Keep ping running in the background (longer than the transfer, since we want latency during it)
ping -i 0.5 -c 200 1.1.1.1 >"$tmp/ping.txt" 2>&1 &
PING=$!
sleep 2
down=$(curl -s -o /dev/null -w '%{speed_download}' "https://speed.cloudflare.com/__down?bytes=${DOWN_BYTES}")
up=$(curl -s -o /dev/null -w '%{speed_upload}' -X POST --data-binary "@$tmp/up.bin" https://speed.cloudflare.com/__up)
sleep 1
kill -INT "$PING" 2>/dev/null || true
wait "$PING" 2>/dev/null || true

# ping median / p95 / max (ping runs alongside the transfer so these reflect it)
stats=$(grep -o 'time=[0-9.]*' "$tmp/ping.txt" | cut -d= -f2 | sort -n | awk '
  { a[NR]=$1 } END { if (NR==0) { print "n=0"; exit }
    printf "n=%d med=%.1f p95=%.1f max=%.1f", NR, a[int((NR+1)/2)], a[int(NR*0.95)], a[NR] }')
printf '%s\tdown=%.2f Mbit/s\tup=%.2f Mbit/s\tping(ms) %s\n' \
  "$LABEL" "$(echo "$down*8/1000000" | bc -l)" "$(echo "$up*8/1000000" | bc -l)" "$stats"
rm -rf "$tmp"

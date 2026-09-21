#!/bin/bash
# measure.sh <label> — この端末から WAN の下り・上りを curl で測り、その最中の 1.1.1.1 への
# ping (ICMP は shaper を素通り) を同時に取る。上限が効いていれば curl が上限に張り付き、
# ping は跳ねないはず。結果は 1 行の TSV (標準出力) と ping の統計 (標準エラー)
#
#   DOWN_BYTES / UP_BYTES で転送量を変える (上限 1 Mbit/s なら 1MB ≒ 8 秒)
set -eu
LABEL=${1:-run}
DOWN_BYTES=${DOWN_BYTES:-2000000}
UP_BYTES=${UP_BYTES:-1000000}
tmp=$(mktemp -d)
head -c "$UP_BYTES" /dev/urandom >"$tmp/up.bin"

# ping を裏で回し続ける (転送中の遅延が知りたいので、転送より長めに)
ping -i 0.5 -c 200 1.1.1.1 >"$tmp/ping.txt" 2>&1 &
PING=$!
sleep 2
down=$(curl -s -o /dev/null -w '%{speed_download}' "https://speed.cloudflare.com/__down?bytes=${DOWN_BYTES}")
up=$(curl -s -o /dev/null -w '%{speed_upload}' -X POST --data-binary "@$tmp/up.bin" https://speed.cloudflare.com/__up)
sleep 1
kill -INT "$PING" 2>/dev/null || true
wait "$PING" 2>/dev/null || true

# ping の中央値 / p95 / max (転送中のものだけ拾えるよう ping は転送と同時に走らせている)
stats=$(grep -o 'time=[0-9.]*' "$tmp/ping.txt" | cut -d= -f2 | sort -n | awk '
  { a[NR]=$1 } END { if (NR==0) { print "n=0"; exit }
    printf "n=%d med=%.1f p95=%.1f max=%.1f", NR, a[int((NR+1)/2)], a[int(NR*0.95)], a[NR] }')
printf '%s\tdown=%.2f Mbit/s\tup=%.2f Mbit/s\tping(ms) %s\n' \
  "$LABEL" "$(echo "$down*8/1000000" | bc -l)" "$(echo "$up*8/1000000" | bc -l)" "$stats"
rm -rf "$tmp"

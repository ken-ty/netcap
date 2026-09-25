#!/bin/bash
# この Linux に netshape を入れる。リポジトリ (linux/ と mac/ がある木) ごと置いてから:
#
#   sudo bash linux/install.sh --boot on     起動時から上限をかける (既定 1/1)
#   sudo bash linux/install.sh --boot off    起動時は素のまま。netcap on で必要なときだけ
#
# 何をするか:
#   /usr/libexec/netcap/netcap-netshape            本体 (root で動く。tc)
#   /usr/libexec/netcap/netcap-agent               netcap が叩く入口 (mac と同じもの。forced command にも使う)
#   /usr/local/bin/netcap-check                    実測 (mac と同じもの。root は要らない)
#   /etc/sudoers.d/netcap-netshape                 呼び出したユーザーに NOPASSWD (本体の決まった動詞だけ)
#   /etc/systemd/system/netcap-netshape.service    --boot on のときだけ
#
# root で動くもの (本体・設定・sudoers) は、置き場所の親ディレクトリまで
# すべて root 所有で group / other が書けないことを確かめてから置く。
set -eu
cd "$(dirname "$0")"

BIN=/usr/libexec/netcap/netcap-netshape
AGENT=/usr/libexec/netcap/netcap-agent
CHECK=/usr/local/bin/netcap-check
CONF=/etc/netcap-netshape.conf
SUDOERS=/etc/sudoers.d/netcap-netshape
UNIT=/etc/systemd/system/netcap-netshape.service

BOOT=
while [ $# -gt 0 ]; do
  case "$1" in
    --boot) BOOT=$2; shift 2 ;;
    *) echo "usage: sudo bash install.sh --boot on|off" >&2; exit 2 ;;
  esac
done
[ "$BOOT" = on ] || [ "$BOOT" = off ] || { echo "usage: sudo bash install.sh --boot on|off" >&2; exit 2; }
[ "$(id -u)" = 0 ] || { echo "sudo で実行してください" >&2; exit 1; }
USER_NAME=${NETCAP_USER:-${SUDO_USER:-}}
[ -n "$USER_NAME" ] || { echo "NETCAP_USER=<user> を指定してください" >&2; exit 1; }
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_.-]*$ ]] || { echo "ユーザー名が読めない: $USER_NAME" >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "そのユーザーはいない: $USER_NAME" >&2; exit 1; }
command -v tc >/dev/null && command -v ip >/dev/null || { echo "tc と ip (iproute2) が要る" >&2; exit 1; }

# dir から / まで、すべて root 所有で group / other が書けないこと
require_root_only() {
  local d uid mode
  d=$(cd -P "$1" && pwd)
  while :; do
    read -r uid mode <<<"$(stat -c '%u %a' "$d")"
    if [ "$uid" != 0 ] || (( 8#$mode & 8#022 )); then
      echo "root 以外が書ける: $d (uid=$uid mode=$mode)。ここには root で動くものを置けない" >&2
      exit 1
    fi
    [ "$d" = / ] && break
    d=$(dirname "$d")
  done
}

install -d -o root -g root -m 0755 /usr/libexec/netcap
mkdir -p /etc/sudoers.d /usr/local/bin
for f in "$BIN" "$CONF" "$SUDOERS" "$UNIT"; do
  require_root_only "$(dirname "$f")"
done

install -o root -g root -m 0755 netcap-netshape "$BIN"
install -o root -g root -m 0755 ../mac/netcap-agent "$AGENT"
install -o root -g root -m 0755 ../mac/netcap-check "$CHECK"

tmp=$(mktemp)
sed "s/__USER__/${USER_NAME}/" sudoers.d/netcap-netshape >"$tmp"
visudo -cf "$tmp" >/dev/null
install -o root -g root -m 0440 "$tmp" "$SUDOERS"
rm -f "$tmp"

if [ "$BOOT" = on ]; then
  install -o root -g root -m 0644 netcap-netshape.service "$UNIT"
  systemctl daemon-reload
  systemctl enable --now netcap-netshape >/dev/null 2>&1
else
  systemctl disable netcap-netshape >/dev/null 2>&1 || true
  rm -f "$UNIT"
  systemctl daemon-reload
fi

echo "installed (boot=${BOOT}, sudoers for ${USER_NAME})"
"$BIN" get
"$BIN" status | head -1

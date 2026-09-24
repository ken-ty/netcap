#!/bin/bash
# この Mac に netshape を入れる。mac/ ディレクトリごと置いてから:
#
#   sudo bash install.sh --boot on     起動時から上限をかける (mini。既定 1/1)
#   sudo bash install.sh --boot off    起動時は素のまま。netcap on で必要なときだけ (MBP)
#
# 何をするか:
#   /usr/local/sbin/ken-ty-netshape            本体 (root が要る)
#   /usr/local/bin/netcap-check                実測 (root は要らない)
#   /etc/pf.anchors/com.ken-ty.netshape        pf のルール
#   /etc/sudoers.d/ken-ty-netshape             呼び出したユーザーに NOPASSWD (本体だけ)
#   /Library/LaunchDaemons/com.ken-ty.netshape.plist   --boot on のときだけ
set -eu
cd "$(dirname "$0")"

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

mkdir -p /usr/local/sbin /usr/local/bin /usr/local/etc /etc/sudoers.d
install -o root -g wheel -m 0755 ken-ty-netshape /usr/local/sbin/ken-ty-netshape
install -o root -g wheel -m 0755 netcap-check /usr/local/bin/netcap-check
install -o root -g wheel -m 0644 com.ken-ty.netshape /etc/pf.anchors/com.ken-ty.netshape

tmp=$(mktemp)
sed "s/__USER__/${USER_NAME}/" sudoers.d/ken-ty-netshape >"$tmp"
visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" /etc/sudoers.d/ken-ty-netshape
rm -f "$tmp"

if [ "$BOOT" = on ]; then
  install -o root -g wheel -m 0644 com.ken-ty.netshape.plist /Library/LaunchDaemons/com.ken-ty.netshape.plist
  launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
  launchctl bootstrap system /Library/LaunchDaemons/com.ken-ty.netshape.plist
  sleep 1
else
  launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
  rm -f /Library/LaunchDaemons/com.ken-ty.netshape.plist
fi

echo "installed (boot=${BOOT}, sudoers for ${USER_NAME})"
/usr/local/sbin/ken-ty-netshape get
/usr/local/sbin/ken-ty-netshape status | head -1

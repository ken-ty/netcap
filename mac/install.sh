#!/bin/bash
# この Mac に netshape を入れる。mac/ ディレクトリごと置いてから:
#
#   sudo bash install.sh --boot on     起動時から上限をかける (mini。既定 1/1)
#   sudo bash install.sh --boot off    起動時は素のまま。netcap on で必要なときだけ (MBP)
#
# 何をするか:
#   /Library/PrivilegedHelperTools/ken-ty-netshape   本体 (root で動く)
#   /usr/local/bin/netcap-check                      実測 (root は要らない)
#   /etc/pf.anchors/com.ken-ty.netshape              pf のルール (アンカー com.apple/ken-ty.netshape に読む)
#   /etc/sudoers.d/ken-ty-netshape                   呼び出したユーザーに NOPASSWD (本体の決まった動詞だけ)
#   /Library/LaunchDaemons/com.ken-ty.netshape.plist --boot on のときだけ
#
# root で動くもの (本体・設定・アンカー・sudoers) は、置き場所の親ディレクトリまで
# すべて root 所有で group / other が書けないことを確かめてから置く。
# 利用者が書けるディレクトリに置くと、中身を差し替えるだけで root が取れるため。
set -eu
cd "$(dirname "$0")"

BIN=/Library/PrivilegedHelperTools/ken-ty-netshape
CONF=/etc/ken-ty-netshape.conf
ANCHOR_FILE=/etc/pf.anchors/com.ken-ty.netshape
SUDOERS=/etc/sudoers.d/ken-ty-netshape
PLIST=/Library/LaunchDaemons/com.ken-ty.netshape.plist

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
# sudoers に埋め込むので、ユーザー名として素直な文字列だけ通す
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_.-]*$ ]] || { echo "ユーザー名が読めない: $USER_NAME" >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "そのユーザーはいない: $USER_NAME" >&2; exit 1; }

# dir から / まで、すべて root 所有で group / other が書けないこと
require_root_only() {
  local d
  d=$(cd -P "$1" && pwd)
  while :; do
    read -r uid mode <<<"$(stat -f '%u %Lp' "$d")"
    if [ "$uid" != 0 ] || (( 8#$mode & 8#022 )); then
      echo "root 以外が書ける: $d (uid=$uid mode=$mode)。ここには root で動くものを置けない" >&2
      exit 1
    fi
    [ "$d" = / ] && break
    d=$(dirname "$d")
  done
}

mkdir -p /Library/PrivilegedHelperTools /etc/pf.anchors /etc/sudoers.d /usr/local/bin
for f in "$BIN" "$CONF" "$ANCHOR_FILE" "$SUDOERS" "$PLIST"; do
  require_root_only "$(dirname "$f")"
done

# 旧版の後始末。旧版は /usr/local/sbin (利用者が書けることがある) に居たので、実行はしない。
# 旧版の on は main ruleset を差し替えていたので、その印が残っていれば /etc/pf.conf に戻す
if [ -f /var/run/com.ken-ty.netshape.pf.conf ]; then
  pfctl -q -f /etc/pf.conf
  dnctl -q pipe delete 1 2 2>/dev/null || true
  rm -f /var/run/com.ken-ty.netshape.pf.conf /var/run/com.ken-ty.netshape.applied
  echo "旧版の pf ルールを外した (main ruleset を /etc/pf.conf に戻した)"
fi
rm -f /usr/local/sbin/ken-ty-netshape
if [ -f /usr/local/etc/ken-ty-netshape.conf ]; then
  # 利用者が書ける場所にあった設定は信用しない。値は netcap set で入れ直す
  echo "旧版の設定を捨てた (/usr/local/etc/ken-ty-netshape.conf):" >&2
  sed 's/^/  /' /usr/local/etc/ken-ty-netshape.conf >&2
  rm -f /usr/local/etc/ken-ty-netshape.conf
fi

install -o root -g wheel -m 0755 ken-ty-netshape "$BIN"
install -o root -g wheel -m 0755 netcap-check /usr/local/bin/netcap-check
install -o root -g wheel -m 0644 com.ken-ty.netshape "$ANCHOR_FILE"

tmp=$(mktemp)
sed "s/__USER__/${USER_NAME}/" sudoers.d/ken-ty-netshape >"$tmp"
visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" "$SUDOERS"
rm -f "$tmp"

if [ "$BOOT" = on ]; then
  install -o root -g wheel -m 0644 com.ken-ty.netshape.plist "$PLIST"
  launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
  launchctl bootstrap system "$PLIST"
  sleep 1
else
  launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
  rm -f "$PLIST"
fi

echo "installed (boot=${BOOT}, sudoers for ${USER_NAME})"
"$BIN" get
"$BIN" status | head -1

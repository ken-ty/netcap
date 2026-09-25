#!/bin/bash
# Install netshape on this Linux. Place the whole repository (the tree with linux/ and mac/), then:
#
#   sudo bash linux/install.sh --boot on     cap from boot (default 1/1)
#   sudo bash linux/install.sh --boot off    no cap at boot; only when needed via netcap on
#
# What it does:
#   /usr/libexec/netcap/netcap-netshape            the shaper (runs as root; tc)
#   /usr/libexec/netcap/netcap-agent               entry point netcap calls (same as mac; also the forced command)
#   /usr/local/bin/netcap-check                    measurement (same as mac; no root needed)
#   /etc/sudoers.d/netcap-netshape                 NOPASSWD for the invoking user (only the shaper's fixed verbs)
#   /etc/systemd/system/netcap-netshape.service    only with --boot on
#
# Root-run files (the shaper, config, sudoers) are placed only after checking that every
# parent directory is root-owned and not writable by group / other.
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
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
USER_NAME=${NETCAP_USER:-${SUDO_USER:-}}
[ -n "$USER_NAME" ] || { echo "set NETCAP_USER=<user>" >&2; exit 1; }
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_.-]*$ ]] || { echo "cannot parse the user name: $USER_NAME" >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "no such user: $USER_NAME" >&2; exit 1; }
command -v tc >/dev/null && command -v ip >/dev/null || { echo "tc and ip (iproute2) are required" >&2; exit 1; }

# Every directory from dir up to / must be root-owned and not writable by group / other
require_root_only() {
  local d uid mode
  d=$(cd -P "$1" && pwd)
  while :; do
    read -r uid mode <<<"$(stat -c '%u %a' "$d")"
    if [ "$uid" != 0 ] || (( 8#$mode & 8#022 )); then
      echo "writable by non-root: $d (uid=$uid mode=$mode); cannot place root-run files here" >&2
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

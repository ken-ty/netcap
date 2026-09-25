#!/bin/bash
# Install netshape on this Mac. Copy the whole mac/ directory, then:
#
#   sudo bash install.sh --boot on     cap from boot (default 1/1)
#   sudo bash install.sh --boot off    no cap at boot; only when needed via netcap on
#
# What it installs:
#   /Library/PrivilegedHelperTools/netcap-netshape   the shaper (runs as root)
#   /Library/PrivilegedHelperTools/netcap-agent      entry point netcap calls (also used as the forced command)
#   /usr/local/bin/netcap-check                      measurement (no root needed)
#   /etc/pf.anchors/netcap-netshape                  pf rules (loaded into anchor com.apple/netcap-netshape)
#   /etc/sudoers.d/netcap-netshape                   NOPASSWD for the invoking user (fixed shaper verbs only)
#   /Library/LaunchDaemons/netcap-netshape.plist     only with --boot on
#
# Root-run files (shaper, config, anchor, sudoers) are placed only after checking that
# every parent directory is root-owned and not writable by group / other.
# In a user-writable directory, swapping the contents would be enough to get root.
set -eu
cd "$(dirname "$0")"

BIN=/Library/PrivilegedHelperTools/netcap-netshape
AGENT=/Library/PrivilegedHelperTools/netcap-agent
CONF=/etc/netcap-netshape.conf
ANCHOR_FILE=/etc/pf.anchors/netcap-netshape
SUDOERS=/etc/sudoers.d/netcap-netshape
PLIST=/Library/LaunchDaemons/netcap-netshape.plist

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
# Embedded in sudoers, so accept only plain user-name strings
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_.-]*$ ]] || { echo "cannot parse the user name: $USER_NAME" >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "no such user: $USER_NAME" >&2; exit 1; }

# From dir up to /, everything must be root-owned and not writable by group / other
require_root_only() {
  local d
  d=$(cd -P "$1" && pwd)
  while :; do
    read -r uid mode <<<"$(stat -f '%u %Lp' "$d")"
    if [ "$uid" != 0 ] || (( 8#$mode & 8#022 )); then
      echo "writable by non-root: $d (uid=$uid mode=$mode); cannot place root-run files here" >&2
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

# Clean up the old version. It lived in /usr/local/sbin (may be user-writable), so never run it.
# Its on replaced the main ruleset; if that marker remains, restore /etc/pf.conf
if [ -f /var/run/com.ken-ty.netshape.pf.conf ]; then
  pfctl -q -f /etc/pf.conf
  dnctl -q pipe delete 1 2 2>/dev/null || true
  rm -f /var/run/com.ken-ty.netshape.pf.conf /var/run/com.ken-ty.netshape.applied
  echo "removed the old version's pf rules (restored the main ruleset from /etc/pf.conf)"
fi
rm -f /usr/local/sbin/ken-ty-netshape
if [ -f /usr/local/etc/ken-ty-netshape.conf ]; then
  # Do not trust a config from a user-writable location. Re-enter the values with netcap set
  echo "discarded the old version's config (/usr/local/etc/ken-ty-netshape.conf):" >&2
  sed 's/^/  /' /usr/local/etc/ken-ty-netshape.conf >&2
  rm -f /usr/local/etc/ken-ty-netshape.conf
fi

# Migrate from the old name (ken-ty-netshape, up to v0.5.0). It also lived in a root-only location,
# so call its off to clean up pf and dnctl, then remove it. The defaults carry over
if [ -e /Library/PrivilegedHelperTools/ken-ty-netshape ]; then
  launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
  /Library/PrivilegedHelperTools/ken-ty-netshape off >/dev/null 2>&1 || true
  if [ -f /etc/ken-ty-netshape.conf ] && [ ! -e "$CONF" ]; then mv /etc/ken-ty-netshape.conf "$CONF"; fi
  rm -f /Library/PrivilegedHelperTools/ken-ty-netshape /etc/ken-ty-netshape.conf \
    /etc/pf.anchors/com.ken-ty.netshape /etc/sudoers.d/ken-ty-netshape \
    /Library/LaunchDaemons/com.ken-ty.netshape.plist
  echo "removed the old name (ken-ty-netshape)"
fi

install -o root -g wheel -m 0755 netcap-netshape "$BIN"
install -o root -g wheel -m 0755 netcap-agent "$AGENT"
install -o root -g wheel -m 0755 netcap-check /usr/local/bin/netcap-check
install -o root -g wheel -m 0644 netcap-netshape.pf "$ANCHOR_FILE"

tmp=$(mktemp)
sed "s/__USER__/${USER_NAME}/" sudoers.d/netcap-netshape >"$tmp"
visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" "$SUDOERS"
rm -f "$tmp"

if [ "$BOOT" = on ]; then
  install -o root -g wheel -m 0644 netcap-netshape.plist "$PLIST"
  launchctl bootout system/netcap-netshape 2>/dev/null || true
  launchctl bootstrap system "$PLIST"
  sleep 1
else
  launchctl bootout system/netcap-netshape 2>/dev/null || true
  rm -f "$PLIST"
fi

echo "installed (boot=${BOOT}, sudoers for ${USER_NAME})"
"$BIN" get
"$BIN" status | head -1

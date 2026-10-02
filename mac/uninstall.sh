#!/bin/bash
# sudo bash uninstall.sh — remove netshape entirely (also lifts the cap)
#   sudo bash uninstall.sh --user — remove only the invoking user from sudoers; everything goes with the last user
set -u
if [ "${1:-}" = --user ]; then
  user=${NETCAP_USER:-${SUDO_USER:-}}
  tmp=$(mktemp)
  bash "$(dirname "$0")/netcap-sudoers" "$(dirname "$0")/sudoers.d/netcap-netshape" /etc/sudoers.d/netcap-netshape \
    remove "$user" >"$tmp" || exit 1
  if [ -s "$tmp" ]; then
    visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; exit 1; }
    install -o root -g wheel -m 0440 "$tmp" /etc/sudoers.d/netcap-netshape
    rm -f "$tmp"
    echo "removed $user; kept for: $(sed -n 's/ ALL=(root) NOPASSWD: NETSHAPE$//p' /etc/sudoers.d/netcap-netshape | paste -sd, - | sed 's/,/, /g')"
    exit 0
  fi
  rm -f "$tmp"  # nobody left: remove everything
fi
launchctl bootout system/netcap-netshape 2>/dev/null || true
/Library/PrivilegedHelperTools/netcap-netshape off 2>/dev/null || true
launchctl bootout system/netcap-netshape-expire 2>/dev/null || true
rm -f /Library/LaunchDaemons/netcap-netshape.plist /Library/PrivilegedHelperTools/netcap-netshape \
  /Library/PrivilegedHelperTools/netcap-netshape-expire.plist /var/run/netcap-netshape.until \
  /Library/PrivilegedHelperTools/netcap-agent \
  /usr/local/bin/netcap-check \
  /etc/pf.anchors/netcap-netshape /etc/netcap-netshape.conf \
  /etc/sudoers.d/netcap-netshape
# Old name (ken-ty-netshape, up to v0.5.0)
launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
/Library/PrivilegedHelperTools/ken-ty-netshape off 2>/dev/null || true
rm -f /Library/LaunchDaemons/com.ken-ty.netshape.plist /Library/PrivilegedHelperTools/ken-ty-netshape \
  /etc/pf.anchors/com.ken-ty.netshape /etc/ken-ty-netshape.conf \
  /etc/sudoers.d/ken-ty-netshape
# Old version's locations (never run it; may be user-writable)
rm -f /usr/local/sbin/ken-ty-netshape /usr/local/etc/ken-ty-netshape.conf
echo "removed"

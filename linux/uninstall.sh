#!/bin/bash
# sudo bash uninstall.sh — remove netshape entirely (also lifts the cap)
#   sudo bash uninstall.sh --user — remove only the invoking user from sudoers; everything goes with the last user
set -u
if [ "${1:-}" = --user ]; then
  user=${NETCAP_USER:-${SUDO_USER:-}}
  tmp=$(mktemp)
  bash "$(dirname "$0")/../mac/netcap-sudoers" "$(dirname "$0")/sudoers.d/netcap-netshape" /etc/sudoers.d/netcap-netshape \
    remove "$user" >"$tmp" || exit 1
  if [ -s "$tmp" ]; then
    visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; exit 1; }
    install -o root -g root -m 0440 "$tmp" /etc/sudoers.d/netcap-netshape
    rm -f "$tmp"
    echo "removed $user; kept for: $(sed -n 's/ ALL=(root) NOPASSWD: NETSHAPE$//p' /etc/sudoers.d/netcap-netshape | paste -sd, - | sed 's/,/, /g')"
    exit 0
  fi
  rm -f "$tmp"  # nobody left: remove everything
fi
systemctl disable netcap-netshape >/dev/null 2>&1 || true
/usr/libexec/netcap/netcap-netshape off 2>/dev/null || true
rm -f /etc/systemd/system/netcap-netshape.service \
  /usr/libexec/netcap/netcap-netshape /usr/libexec/netcap/netcap-agent \
  /usr/local/bin/netcap-check /etc/netcap-netshape.conf /etc/sudoers.d/netcap-netshape
rmdir /usr/libexec/netcap 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true
echo "removed"

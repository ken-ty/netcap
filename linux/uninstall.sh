#!/bin/bash
# sudo bash uninstall.sh — remove netshape entirely (also lifts the cap)
set -u
systemctl disable netcap-netshape >/dev/null 2>&1 || true
/usr/libexec/netcap/netcap-netshape off 2>/dev/null || true
rm -f /etc/systemd/system/netcap-netshape.service \
  /usr/libexec/netcap/netcap-netshape /usr/libexec/netcap/netcap-agent \
  /usr/local/bin/netcap-check /etc/netcap-netshape.conf /etc/sudoers.d/netcap-netshape
rmdir /usr/libexec/netcap 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true
echo "removed"

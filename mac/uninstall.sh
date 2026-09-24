#!/bin/bash
# sudo bash uninstall.sh — netshape を全部外す (上限も解除する)
set -u
launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
/usr/local/sbin/ken-ty-netshape off 2>/dev/null || true
rm -f /Library/LaunchDaemons/com.ken-ty.netshape.plist /usr/local/sbin/ken-ty-netshape \
  /usr/local/bin/netcap-check \
  /etc/pf.anchors/com.ken-ty.netshape /usr/local/etc/ken-ty-netshape.conf \
  /etc/sudoers.d/ken-ty-netshape
echo "removed"

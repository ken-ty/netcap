#!/bin/bash
# sudo bash uninstall.sh — netshape を全部外す (上限も解除する)
set -u
launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
/Library/PrivilegedHelperTools/ken-ty-netshape off 2>/dev/null || true
rm -f /Library/LaunchDaemons/com.ken-ty.netshape.plist /Library/PrivilegedHelperTools/ken-ty-netshape \
  /Library/PrivilegedHelperTools/netcap-agent \
  /usr/local/bin/netcap-check \
  /etc/pf.anchors/com.ken-ty.netshape /etc/ken-ty-netshape.conf \
  /etc/sudoers.d/ken-ty-netshape
# 旧版の置き場所 (実行はしない。利用者が書けることがある)
rm -f /usr/local/sbin/ken-ty-netshape /usr/local/etc/ken-ty-netshape.conf
echo "removed"

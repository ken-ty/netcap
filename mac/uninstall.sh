#!/bin/bash
# sudo bash uninstall.sh — netshape を全部外す (上限も解除する)
set -u
launchctl bootout system/netcap-netshape 2>/dev/null || true
/Library/PrivilegedHelperTools/netcap-netshape off 2>/dev/null || true
rm -f /Library/LaunchDaemons/netcap-netshape.plist /Library/PrivilegedHelperTools/netcap-netshape \
  /Library/PrivilegedHelperTools/netcap-agent \
  /usr/local/bin/netcap-check \
  /etc/pf.anchors/netcap-netshape /etc/netcap-netshape.conf \
  /etc/sudoers.d/netcap-netshape
# 旧名 (ken-ty-netshape。v0.5.0 まで)
launchctl bootout system/com.ken-ty.netshape 2>/dev/null || true
/Library/PrivilegedHelperTools/ken-ty-netshape off 2>/dev/null || true
rm -f /Library/LaunchDaemons/com.ken-ty.netshape.plist /Library/PrivilegedHelperTools/ken-ty-netshape \
  /etc/pf.anchors/com.ken-ty.netshape /etc/ken-ty-netshape.conf \
  /etc/sudoers.d/ken-ty-netshape
# 旧版の置き場所 (実行はしない。利用者が書けることがある)
rm -f /usr/local/sbin/ken-ty-netshape /usr/local/etc/ken-ty-netshape.conf
echo "removed"

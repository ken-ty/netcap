#!/bin/bash
# sudo bash uninstall.sh — remove netshape entirely (also lifts the cap)
set -u
launchctl bootout system/netcap-netshape 2>/dev/null || true
/Library/PrivilegedHelperTools/netcap-netshape off 2>/dev/null || true
rm -f /Library/LaunchDaemons/netcap-netshape.plist /Library/PrivilegedHelperTools/netcap-netshape \
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

#!/bin/bash
# README の Quick Start と docs/host-setup.md を macOS の実機でなぞる。sudo が要る (CI の macOS ランナー向け)
#
#   bash tests/e2e-mac.sh
set -u
cd "$(dirname "$0")/.."
fail=0
expect() { # expect <説明> <正規表現> <コマンド...>
  local what=$1 re=$2 out
  shift 2
  out=$("$@" 2>&1)
  if [[ "$out" =~ $re ]]; then echo "ok   $what"; else echo "FAIL $what"; echo "$out" | sed 's/^/     /'; fail=1; fi
}
gone() { [ ! -e "$1" ] && echo gone || echo "still there: $1"; }

conf=$(mktemp -d)
export NETCAP_CONFIG_DIR=$conf
echo "self mac -" >"$conf/hosts"
printf 'p  self=2/3\nnone  self=off\n' >"$conf/profiles"
netcap() { bin/netcap "$@"; }

# v0.5.0 の旧名から上げる (docs/host-setup.md)
old=$(mktemp -d)
git archive v0.5.0 mac | tar -x -C "$old"
sudo bash "$old/mac/install.sh" --boot on >/dev/null
expect "旧名から上げると旧名が消える" "旧名 \(ken-ty-netshape\) を外した" sudo bash mac/install.sh --boot off
expect "旧名の本体が残らない" "^gone$" gone /Library/PrivilegedHelperTools/ken-ty-netshape
expect "旧名の LaunchDaemon が残らない" "^gone$" gone /Library/LaunchDaemons/com.ken-ty.netshape.plist

# docs/host-setup.md の macOS
sudo bash mac/install.sh --boot on >/dev/null
expect "--boot on で LaunchDaemon が入る" "netcap-netshape" sudo launchctl print system/netcap-netshape
expect "get: 既定 1/1、boot on" "self +ok +1/1 Mbit/s +on" netcap get self
sudo bash mac/install.sh --boot off >/dev/null
expect "get: boot off" "self +ok +1/1 Mbit/s +off" netcap get self
expect "status: 最初は off" "self +ok +off " netcap status self

# README の Usage
expect "on: 既定の値でかかる" "self +ok +on +1 Mbit/s +1 Mbit/s\*" netcap on self
expect "on --up --down: 今回だけの値" "self +ok +on +2 Mbit/s +3 Mbit/s\*" netcap on self --up 2 --down 3
expect "on の値は既定を変えない" "1/1 Mbit/s" netcap get self
expect "set: 既定を書き換える" "self +ok +on +4 Mbit/s +5 Mbit/s\*" netcap set self --up 4 --down 5
expect "set: get に出る" "4/5 Mbit/s" netcap get self
expect "off" "self +ok +off " netcap off self
expect "use: プロファイルの値" "profile: p.*self +ok +on +2 Mbit/s +3 Mbit/s\*" netcap use p
expect "use none" "self +ok +off " netcap use none
expect "--json" '"reach": "ok"' netcap status self --json

# docs/design.md: pf と dnctl は自分の分だけ触る
expect "on は自分のアンカーにだけルールを入れる" "pipe 1" bash -c "bin/netcap on self >/dev/null; sudo pfctl -a com.apple/netcap-netshape -s dummynet 2>/dev/null"
expect "/etc/pf.conf は差し替えない" 'dummynet-anchor "com.apple/\*"' bash -c "sudo pfctl -s dummynet 2>/dev/null"
bin/netcap off self >/dev/null

# docs/host-setup.md: forced command で許可していない動詞は denied
expect "--allow にない動詞は拒む" "netcap-agent: .*on" env SSH_ORIGINAL_COMMAND="netcap-agent on" /Library/PrivilegedHelperTools/netcap-agent --allow "status get"
expect "引数はシェルとして解釈しない" "netcap-agent: 引数は数値だけ" env SSH_ORIGINAL_COMMAND='on $(id) 1' /Library/PrivilegedHelperTools/netcap-agent --allow "on"

# docs/design.md: root で動くものは root だけが書ける
expect "本体は root 所有で他人が書けない" "^0 755$" stat -f '%u %Lp' /Library/PrivilegedHelperTools/netcap-netshape

# 外す
sudo bash mac/uninstall.sh >/dev/null
for p in /Library/PrivilegedHelperTools/netcap-netshape /Library/PrivilegedHelperTools/netcap-agent \
  /usr/local/bin/netcap-check /etc/pf.anchors/netcap-netshape /etc/sudoers.d/netcap-netshape \
  /Library/LaunchDaemons/netcap-netshape.plist; do
  expect "uninstall: $p" "^gone$" gone "$p"
done

exit $fail

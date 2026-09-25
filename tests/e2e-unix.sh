#!/bin/bash
# README の Quick Start と docs/host-setup.md を macOS / Linux の実機でなぞる。sudo が要る (CI のランナー向け)
#
#   bash tests/e2e-unix.sh
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

if [ "$(uname)" = Darwin ]; then
  os=mac
  AGENT=/Library/PrivilegedHelperTools/netcap-agent
  NETSHAPE=/Library/PrivilegedHelperTools/netcap-netshape
  PATHS="$NETSHAPE $AGENT /usr/local/bin/netcap-check /etc/pf.anchors/netcap-netshape
    /etc/sudoers.d/netcap-netshape /Library/LaunchDaemons/netcap-netshape.plist"
  boot_on() { sudo launchctl print system/netcap-netshape; }
else
  os=linux
  AGENT=/usr/local/libexec/netcap/netcap-agent
  NETSHAPE=/usr/local/libexec/netcap/netcap-netshape
  PATHS="$NETSHAPE $AGENT /usr/local/bin/netcap-check /etc/sudoers.d/netcap-netshape
    /etc/systemd/system/netcap-netshape.service"
  boot_on() { systemctl is-enabled netcap-netshape; }
fi

conf=$(mktemp -d)
export NETCAP_CONFIG_DIR=$conf
echo "self $os -" >"$conf/hosts"
printf 'p  self=2/3\nnone  self=off\n' >"$conf/profiles"
netcap() { bin/netcap "$@"; }

if [ $os = mac ]; then
  # v0.5.0 の旧名から上げる (docs/host-setup.md)
  old=$(mktemp -d)
  git archive v0.5.0 mac | tar -x -C "$old"
  sudo bash "$old/mac/install.sh" --boot on >/dev/null
  expect "旧名から上げると旧名が消える" "旧名 \(ken-ty-netshape\) を外した" sudo bash mac/install.sh --boot off
  expect "旧名の本体が残らない" "^gone$" gone /Library/PrivilegedHelperTools/ken-ty-netshape
  expect "旧名の LaunchDaemon が残らない" "^gone$" gone /Library/LaunchDaemons/com.ken-ty.netshape.plist
fi

# docs/host-setup.md
sudo bash $os/install.sh --boot on >/dev/null
expect "--boot on で起動時に動く" "netcap-netshape|enabled" boot_on
expect "get: 既定 1/1、boot on" "self +ok +1/1 Mbit/s +on" netcap get self
sudo bash $os/install.sh --boot off >/dev/null
expect "get: boot off" "self +ok +1/1 Mbit/s +off" netcap get self

# README の Usage (mac の下りは記録から読むので * が付く)
expect "on: 既定の値でかかる" "self +ok +on +1 Mbit/s +1 Mbit/s\*? " netcap on self
expect "on --up --down: 今回だけの値" "self +ok +on +2 Mbit/s +3 Mbit/s\*? " netcap on self --up 2 --down 3
expect "on の値は既定を変えない" "1/1 Mbit/s" netcap get self
expect "set: 既定を書き換え、かかっていれば張り直す" "self +ok +on +4 Mbit/s +5 Mbit/s\*? " netcap set self --up 4 --down 5
expect "set: get に出る" "4/5 Mbit/s" netcap get self
expect "off" "self +ok +off " netcap off self
expect "use: プロファイルの値" "profile: p.*self +ok +on +2 Mbit/s +3 Mbit/s\*? " netcap use p
expect "use none" "self +ok +off " netcap use none
expect "--json" '"reach": "ok"' netcap status self --json

# docs/design.md: 自分の分だけ触る
bin/netcap on self >/dev/null
if [ $os = mac ]; then
  expect "on は自分のアンカーにだけルールを入れる" "pipe 1" sudo pfctl -a com.apple/netcap-netshape -s dummynet
  expect "/etc/pf.conf は差し替えない" 'dummynet-anchor "com.apple/\*"' sudo pfctl -s dummynet
else
  dev=$(ip route get 1.1.1.1 | sed -n 's/.* dev \([^ ]*\).*/\1/p')
  expect "root qdisc は自分の HTB" "qdisc htb ca9: root" tc qdisc show dev "$dev"
  expect "下りは ifb-netcap で絞る" "qdisc htb .* root" tc qdisc show dev ifb-netcap
  bin/netcap off self >/dev/null
  expect "off で root qdisc が既定に戻る" "^0$" bash -c "tc qdisc show dev $dev | grep -c ca9: || true"
  expect "off で ifb-netcap が消える" "^gone$" bash -c "ip link show ifb-netcap >/dev/null 2>&1 && echo there || echo gone"
fi
bin/netcap off self >/dev/null

# docs/host-setup.md: forced command で許可していない動詞は denied
expect "--allow にない動詞は拒む" "netcap-agent: .*on" env SSH_ORIGINAL_COMMAND="netcap-agent on" $AGENT --allow "status get"
expect "引数はシェルとして解釈しない" "netcap-agent: 引数は数値だけ" env SSH_ORIGINAL_COMMAND='on $(id) 1' $AGENT --allow "on"

# docs/design.md: root で動くものは root だけが書ける
if [ $os = mac ]; then mode=$(stat -f '%u %Lp' $NETSHAPE); else mode=$(stat -c '%u %a' $NETSHAPE); fi
expect "本体は root 所有で他人が書けない" "^0 755$" echo "$mode"

# 外す
sudo bash $os/uninstall.sh >/dev/null
for p in $PATHS; do
  expect "uninstall: $p" "^gone$" gone "$p"
done

exit $fail

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Run actual package hooks in a disposable official rootfs, never on a router.
set -eu
umask 022
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo on Linux x86_64.' >&2; exit 1; }
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
out="$repo/dist/sdk"
url=https://downloads.immortalwrt.org/releases/25.12.0/targets/x86/64/immortalwrt-25.12.0-x86-64-rootfs.tar.gz
rootfs_sha=02b2466f740778962f89e48b2a9873ec6293a094626678006e2fd3ba7d83e7d9
work=$(mktemp -d /tmp/mori-native-test.XXXXXXXX)
touch "$work/.mori-owned-workdir"
cleanup() {
    case "$work" in /tmp/mori-native-test.*)
        [ -f "$work/.mori-owned-workdir" ] && rm -rf -- "$work"
        ;;
    esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
curl --fail --location --retry 4 --connect-timeout 30 --output "$work/rootfs.tar.gz" "$url"
printf '%s  %s\n' "$rootfs_sha" "$work/rootfs.tar.gz" | sha256sum -c -
mkdir "$work/rootfs"
tar -xzf "$work/rootfs.tar.gz" -C "$work/rootfs"
root="$work/rootfs"
mkdir -p "$root/tmp" "$root/dev" "$root/etc/config" "$root/root"
[ -e "$root/dev/null" ] || mknod -m 666 "$root/dev/null" c 1 3
[ -e "$root/dev/urandom" ] || mknod -m 666 "$root/dev/urandom" c 1 9
find "$out" -maxdepth 1 -type f -name 'luci-theme-mori-*.apk' > "$work/packages"
[ "$(wc -l < "$work/packages")" -eq 1 ]
cp "$(cat "$work/packages")" "$root/tmp/mori.apk"
mkdir -p "$root/tmp/mori-keys"
cp "$out/mori-sdk-signing-public.pem" "$root/tmp/mori-keys/"
cp "$out/hooks/post-upgrade" "$root/root/mori-post-upgrade"

# Use synthetic settings only. This rootfs is never booted, has no mounted
# host filesystems, and receives no router credentials or configuration.
cat > "$root/etc/config/luci" <<'CONFIG'
config core 'main'
    option mediaurlbase '/luci-static/bootstrap'
    option lang 'auto'
config internal 'themes'
    option Bootstrap '/luci-static/bootstrap'
CONFIG
cat > "$root/etc/config/network" <<'CONFIG'
config interface 'lan'
    option proto 'static'
    option ipaddr '192.0.2.1'
CONFIG
cat > "$root/root/mori-test" <<'TEST'
#!/bin/sh
set -eu
assert_equal() { [ "$1" = "$2" ] || { echo "FAIL: $3 ($1 != $2)" >&2; exit 1; }; }
command -v apk
test -f /usr/share/ucode/luci/template/themes/bootstrap/header.ut
uci set network.lan.ipaddr=192.0.2.2
network_before=$(sha256sum /etc/config/network)
network_delta_before=$(uci changes network)
other_before=$(find /etc/config -type f ! -name luci -exec sha256sum '{}' ';' | sort)

apk --keys-dir /tmp/mori-keys --no-network --repositories-file /dev/null verify /tmp/mori.apk
apk --keys-dir /tmp/mori-keys --no-network --repositories-file /dev/null add /tmp/mori.apk
assert_equal "$(uci get luci.themes.Mori)" /luci-static/mori 'Mori registration'
assert_equal "$(uci get luci.main.mediaurlbase)" /luci-static/bootstrap 'install preserves theme'
test -f /www/luci-static/mori/mori.css
test -f /www/luci-static/resources/menu-mori.js
test -f /usr/libexec/mori-register
for template in /usr/share/ucode/luci/template/themes/mori/*.ut; do
    ucode -T -c -o /tmp/mori-template.uc "$template"
done
echo 'PASS: native APK install, registration, payload and template compilation'

# Active selection survives the exact SDK-generated upgrade wrapper.
uci set luci.main.mediaurlbase=/luci-static/mori
uci commit luci
sh /root/mori-post-upgrade
assert_equal "$(uci get luci.main.mediaurlbase)" /luci-static/mori 'upgrade preserves active theme'
echo 'PASS: generated post-upgrade hook preserves active Mori'

# A pending LuCI draft is neither committed nor discarded by package hooks.
uci set luci.main.lang=zh_cn
luci_before=$(sha256sum /etc/config/luci)
luci_delta_before=$(uci changes luci)
if sh /usr/libexec/mori-register --prepare-remove; then
    echo 'FAIL: removal preparation accepted pending LuCI drafts' >&2
    exit 1
fi
sh /root/mori-post-upgrade
assert_equal "$(sha256sum /etc/config/luci)" "$luci_before" 'draft guard config'
assert_equal "$(uci changes luci)" "$luci_delta_before" 'draft guard pending edits'
uci revert luci
echo 'PASS: pending LuCI drafts preserved and explicit removal refused'

# A missing fallback must leave the active configuration intact.
mv /usr/share/ucode/luci/template/themes/bootstrap/header.ut /tmp/bootstrap-header.ut
luci_before=$(sha256sum /etc/config/luci)
if sh /usr/libexec/mori-register --prepare-remove; then
    echo 'FAIL: removal preparation accepted missing fallback' >&2
    exit 1
fi
assert_equal "$(sha256sum /etc/config/luci)" "$luci_before" 'missing fallback config'
mv /tmp/bootstrap-header.ut /usr/share/ucode/luci/template/themes/bootstrap/header.ut
echo 'PASS: missing fallback leaves active Mori untouched'

sh /usr/libexec/mori-register --prepare-remove
assert_equal "$(uci get luci.main.mediaurlbase)" /luci-static/bootstrap 'fallback before uninstall'
apk --no-network --repositories-file /dev/null del luci-theme-mori
test ! -e /www/luci-static/mori/mori.css
test ! -e /usr/libexec/mori-register
test -z "$(uci -q get luci.themes.Mori || true)"
assert_equal "$(uci get luci.main.mediaurlbase)" /luci-static/bootstrap 'uninstall preserves fallback'
assert_equal "$(sha256sum /etc/config/network)" "$network_before" 'network configuration'
assert_equal "$(uci changes network)" "$network_delta_before" 'pending network edits'
assert_equal "$(find /etc/config -type f ! -name luci -exec sha256sum '{}' ';' | sort)" "$other_before" 'all non-LuCI configurations'
echo 'PASS: native uninstall, usable fallback, unchanged non-LuCI configuration and pending network edits'
TEST

if chroot "$root" /bin/sh /root/mori-test > "$work/smoke.log" 2>&1; then
    cat "$work/smoke.log"
else
    cat "$work/smoke.log" >&2
    exit 1
fi
{
    printf 'Rootfs: %s\nSHA256: %s\n' "$url" "$rootfs_sha"
    printf 'Environment: disposable chroot; no services booted, no host mounts, synthetic configuration.\n'
    cat "$work/smoke.log"
} > "$out/native-smoke-test.txt"
(
    cd "$out"
    find . -type f ! -name SHA256SUMS -print | LC_ALL=C sort | while IFS= read -r file; do sha256sum "${file#./}"; done > SHA256SUMS
)

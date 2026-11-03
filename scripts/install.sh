#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Install an unpacked Mori release. No services are restarted.
set -eu
umask 077

fail() { printf 'Mori: %s\n' "$*" >&2; exit 1; }
activate=0
case "${1:-}" in
  '') ;;
  --activate) activate=1; shift ;;
  -h|--help) printf 'Usage: sh scripts/install.sh [--activate]\n'; exit 0 ;;
  *) fail 'Unknown option. Use --activate to select Mori after installation.' ;;
esac
[ "$#" -eq 0 ] || fail 'Unexpected arguments.'

# Test harness only: never redirects an ordinary installation.
target=${MORI_TEST_ROOT:-}
if [ -n "$target" ]; then
  [ -f "$target/.mori-test-root" ] || fail 'Invalid test root.'
  target=$(cd "$target" && pwd -P)
  [ "$target" != / ] || fail 'Test root cannot be /.'
else
  [ "$(id -u)" = 0 ] || fail 'Run as root on the router.'
fi
for tool in uci ucode sha256sum find sort cmp mktemp; do
  command -v "$tool" >/dev/null 2>&1 || fail "Missing required command: $tool"
done
[ -f "$target/usr/share/ucode/luci/runtime.uc" ] || fail 'This release requires ucode-based LuCI.'
[ -f "$target/etc/config/luci" ] || fail 'LuCI configuration is missing.'
[ ! -L "$target/etc/config/luci" ] || fail 'Refusing a symlinked LuCI configuration.'
for record in "$target/usr/lib/opkg/info/luci-theme-mori.control" "$target/lib/apk/packages/luci-theme-mori.list"; do
  [ ! -e "$record" ] || fail 'Mori is package-managed; upgrade it with the same package manager.'
done
if [ -z "$target" ]; then
  if command -v apk >/dev/null 2>&1 && apk info -e luci-theme-mori >/dev/null 2>&1; then fail 'Mori is package-managed; use apk to upgrade it.'; fi
  if command -v opkg >/dev/null 2>&1 && opkg status luci-theme-mori 2>/dev/null | grep -q '^Status: .* installed'; then fail 'Mori is package-managed; use opkg to upgrade it.'; fi
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
release=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
payload=$release/rootfs
manifest=$release/manifest.sha256
[ -d "$payload" ] && [ -s "$manifest" ] && [ -s "$release/VERSION" ] || fail 'Run this script from an unpacked release archive, not the source tree.'
[ -f "$script_dir/rollback.sh" ] || fail 'The release rollback script is missing.'

mkdir -p "$target/tmp"
work=$(mktemp -d "$target/tmp/mori-install.XXXXXX")
backup=
changed=0
config_swapped=0
finished=0
cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  set +e
  if [ "$changed" = 1 ] && [ "$finished" = 0 ]; then
    if [ "$config_swapped" = 1 ] && cmp -s "$work/config/$config_name" "$target/etc/config/luci"; then
      cp -p "$backup/luci.before" "$target/etc/config/.luci-mori-recover-$$" && mv "$target/etc/config/.luci-mori-recover-$$" "$target/etc/config/luci" || true
    fi
    while IFS= read -r path; do
      if [ -f "$backup/files/$path" ]; then
        cp -p "$backup/files/$path" "$target/$path.mori-recover-$$" && mv "$target/$path.mori-recover-$$" "$target/$path" || true
      else
        rm -f "$target/$path"
      fi
      rm -f "$target/$path.mori-next-$$"
    done < "$work/changed.paths"
    printf 'Mori: installation interrupted; prior files restored where possible. Backup: %s\n' "$backup" >&2
  fi
  rm -f "$target/etc/config/.luci-mori-next-$$"
  case "$work" in "$target"/tmp/mori-install.*) rm -rf "$work" ;; esac
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

valid_path() {
  case "$1" in ''|/*|*..*|*//*|*[!A-Za-z0-9_./-]*) return 1 ;; esac
  case "$1" in
    www/luci-static/mori/*|usr/share/ucode/luci/template/themes/mori/*.ut|www/luci-static/resources/menu-mori.js) return 0 ;;
    *) return 1 ;;
  esac
}
check_parents() {
  part=$1
  while [ "$part" != "$target" ] && [ "$part" != / ] && [ -n "$part" ]; do
    [ ! -L "$part" ] || fail "Refusing symlink in destination: $part"
    part=${part%/*}
  done
}
[ -z "$(find "$payload" -type l -print)" ] || fail 'Symlinks are not allowed in a release payload.'
[ -z "$(find "$payload" ! -type d ! -type f -print)" ] || fail 'Only regular files and directories are allowed in a release payload.'
: > "$work/paths"
while read -r digest path extra; do
  [ -z "${extra:-}" ] && [ "${#digest}" -eq 64 ] || fail 'Malformed checksum manifest.'
  case "$digest" in *[!0-9a-f]*) fail 'Malformed checksum digest.' ;; esac
  valid_path "$path" || fail "Unexpected release path: $path"
  [ -f "$payload/$path" ] || fail "Missing release file: $path"
  printf '%s\n' "$path" >> "$work/paths"
  check_parents "$target/$path"
done < "$manifest"
sort "$work/paths" > "$work/paths.sorted"
sort -u "$work/paths" > "$work/paths.unique"
cmp -s "$work/paths.sorted" "$work/paths.unique" || fail 'Duplicate paths in checksum manifest.'
(cd "$payload" && find . -type f | sed 's|^./||' | sort) > "$work/actual.paths"
cmp -s "$work/paths.sorted" "$work/actual.paths" || fail 'Payload files and checksum manifest differ.'
(cd "$payload" && sha256sum -c "$manifest") > "$work/checksums.log" || fail 'Release checksum verification failed.'
for required in www/luci-static/mori/mori.css www/luci-static/mori/theme.js www/luci-static/resources/menu-mori.js usr/share/ucode/luci/template/themes/mori/header.ut usr/share/ucode/luci/template/themes/mori/header_login.ut usr/share/ucode/luci/template/themes/mori/footer.ut usr/share/ucode/luci/template/themes/mori/footer_login.ut usr/share/ucode/luci/template/themes/mori/sysauth.ut usr/share/ucode/luci/template/themes/mori/out_header_login.ut; do
  grep -Fxq "$required" "$work/paths" || fail "Incomplete theme: $required"
done
for template in "$payload"/usr/share/ucode/luci/template/themes/mori/*.ut; do
  ucode -e 'loadfile(ARGV[0], {raw_mode:false});' "$template" || fail "Template compilation failed: ${template##*/}"
done

live_uci() {
  if [ -n "$target" ]; then uci -c "$target/etc/config" "$@"; else uci "$@"; fi
}
[ -z "$(live_uci -q changes luci)" ] || fail 'LuCI has uncommitted changes; finish or discard them before installing.'
live_uci -q get luci.themes >/dev/null || fail 'The LuCI themes section is missing.'
check_parents "$target/root/mori-backups"
mkdir -p "$target/root/mori-backups"
chmod 700 "$target/root/mori-backups"
backup=$target/root/mori-backups/$(date +%Y%m%d-%H%M%S)-$$
mkdir -m 700 "$backup" "$backup/files"
cp "$script_dir/rollback.sh" "$backup/rollback.sh"
chmod 700 "$backup/rollback.sh"
cp "$release/VERSION" "$backup/version"
cp "$manifest" "$backup/installed.sha256"
cp -p "$target/etc/config/luci" "$backup/luci.before"
if live_uci -q get luci.main.mediaurlbase > "$backup/previous-media"; then touch "$backup/previous-media.present"; fi
if live_uci -q get luci.themes.Mori > "$backup/previous-registration"; then touch "$backup/previous-registration.present"; fi
if [ "$activate" = 1 ]; then
  previous=$(cat "$backup/previous-media")
  case "$previous" in /luci-static/*) previous_theme=${previous#/luci-static/} ;; *) fail 'No valid previous theme is configured; select a working fallback first.' ;; esac
  case "$previous_theme" in ''|*[!A-Za-z0-9_-]*) fail 'Unsupported previous theme identifier.' ;; esac
  [ -d "$target/www/luci-static/$previous_theme" ] || fail 'The previous theme assets are missing.'
  [ -f "$target/usr/share/ucode/luci/template/themes/$previous_theme/header.ut" ] || [ -f "$target/usr/lib/lua/luci/view/themes/$previous_theme/header.htm" ] || fail 'The previous theme templates are missing.'
fi
: > "$backup/previous.paths"
: > "$work/changed.paths"
while IFS= read -r path; do
  if [ -e "$target/$path" ]; then
    [ -f "$target/$path" ] || fail "Destination is not a regular file: $path"
    mkdir -p "$backup/files/${path%/*}"
    cp -p "$target/$path" "$backup/files/$path"
    printf '%s\n' "$path" >> "$backup/previous.paths"
  fi
done < "$work/paths"
(cd "$backup/files" && while IFS= read -r path; do sha256sum "$path"; done < "$backup/previous.paths") > "$backup/previous.sha256"

# Edit a uniquely named temporary UCI package. This does not load or commit
# the user's luci delta file. Recheck the live config before swapping it.
config_name=mori_install_$$
[ ! -e "$target/tmp/.uci/$config_name" ] || fail 'Unexpected staging-package delta exists.'
mkdir "$work/config" "$work/delta"
cp "$backup/luci.before" "$work/config/$config_name"
staged_uci() { uci -c "$work/config" -t "$work/delta" "$@"; }
staged_uci set "$config_name.themes.Mori=/luci-static/mori"
if [ "$activate" = 1 ]; then staged_uci set "$config_name.main.mediaurlbase=/luci-static/mori"; fi
staged_uci commit "$config_name"
staged_uci -q get "$config_name.main.mediaurlbase" > "$backup/expected-media" || true
printf '/luci-static/mori\n' > "$backup/expected-registration"

while IFS= read -r path; do
  (umask 022; mkdir -p "$target/${path%/*}")
  cp "$payload/$path" "$target/$path.mori-next-$$"
  chmod 644 "$target/$path.mori-next-$$"
  printf '%s\n' "$path" >> "$work/changed.paths"
  changed=1
  mv "$target/$path.mori-next-$$" "$target/$path"
done < "$work/paths"
(cd "${target:-/}" && sha256sum -c "$backup/installed.sha256") > "$backup/verification.log" || fail 'Installed files failed verification.'
[ -z "$(live_uci -q changes luci)" ] || fail 'LuCI changes appeared during installation; configuration was not changed.'
cmp -s "$backup/luci.before" "$target/etc/config/luci" || fail 'LuCI configuration changed during installation; configuration was not replaced.'
cp -p "$target/etc/config/luci" "$target/etc/config/.luci-mori-next-$$"
cat "$work/config/$config_name" > "$target/etc/config/.luci-mori-next-$$"
config_swapped=1
mv "$target/etc/config/.luci-mori-next-$$" "$target/etc/config/luci"
date -Iseconds > "$backup/complete"
finished=1
printf 'Mori %s installed and registered.\n' "$(cat "$release/VERSION")"
if [ "$activate" = 1 ]; then printf 'Mori is now selected. Refresh LuCI to load it.\n'; else printf 'The selected theme was preserved. Select Mori in System > System > Language and Style.\n'; fi
printf 'No services restarted. Rollback: sh %s/rollback.sh\n' "$backup"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Run the copy stored in an installation backup, not this source-tree copy.
set -eu
umask 077
fail() { printf 'Mori rollback: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || fail 'Run rollback.sh from the required installation backup without arguments.'
target=${MORI_TEST_ROOT:-}
if [ -n "$target" ]; then
  [ -f "$target/.mori-test-root" ] || fail 'Invalid test root.'
  target=$(cd "$target" && pwd -P)
  [ "$target" != / ] || fail 'Test root cannot be /.'
else
  [ "$(id -u)" = 0 ] || fail 'Run as root on the router.'
fi
backup=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
case "$backup" in "$target"/root/mori-backups/*) ;; *) fail 'Use rollback.sh from /root/mori-backups/<installation>/.' ;; esac
[ -f "$backup/complete" ] || fail 'This is not a completed installation backup; inspect it manually.'
[ ! -f "$backup/rolled-back" ] || { printf 'This installation has already been rolled back.\n'; exit 0; }
for required in installed.sha256 previous.paths previous.sha256 previous-media previous-registration expected-media expected-registration; do
  [ -f "$backup/$required" ] || fail "Incomplete backup: $required"
done
for record in "$target/usr/lib/opkg/info/luci-theme-mori.control" "$target/lib/apk/packages/luci-theme-mori.list"; do
  [ ! -e "$record" ] || fail 'Mori is now package-managed; use the package manager instead.'
done
if [ -z "$target" ]; then
  if command -v apk >/dev/null 2>&1 && apk info -e luci-theme-mori >/dev/null 2>&1; then fail 'Mori is now package-managed; use apk instead.'; fi
  if command -v opkg >/dev/null 2>&1 && opkg status luci-theme-mori 2>/dev/null | grep -q '^Status: .* installed'; then fail 'Mori is now package-managed; use opkg instead.'; fi
fi
valid_path() {
  case "$1" in ''|/*|*..*|*//*|*[!A-Za-z0-9_./-]*) return 1 ;; esac
  case "$1" in www/luci-static/mori/*|usr/share/ucode/luci/template/themes/mori/*.ut|www/luci-static/resources/menu-mori.js) return 0 ;; *) return 1 ;; esac
}
check_parents() {
  part=$1
  while [ "$part" != "$target" ] && [ "$part" != / ] && [ -n "$part" ]; do
    [ ! -L "$part" ] || fail "Refusing symlink in destination: $part"
    part=${part%/*}
  done
}
live_uci() { if [ -n "$target" ]; then uci -c "$target/etc/config" "$@"; else uci "$@"; fi; }
[ -z "$(live_uci -q changes luci)" ] || fail 'LuCI has uncommitted changes.'
current_media=$(live_uci -q get luci.main.mediaurlbase || true)
[ "$current_media" = "$(cat "$backup/expected-media")" ] || fail 'The selected theme has changed since this installation; nothing was restored.'
[ "$(live_uci -q get luci.themes.Mori || true)" = "$(cat "$backup/expected-registration")" ] || fail 'Mori registration has changed; nothing was restored.'
while read -r digest path extra; do
  [ -z "${extra:-}" ] && [ "${#digest}" -eq 64 ] || fail 'Malformed backup manifest.'
  case "$digest" in *[!0-9a-f]*) fail 'Malformed backup digest.' ;; esac
  valid_path "$path" || fail "Unexpected managed path: $path"
  check_parents "$target/$path"
done < "$backup/installed.sha256"
(cd "${target:-/}" && sha256sum -c "$backup/installed.sha256") >/dev/null || fail 'Mori files changed after installation; refusing to overwrite a newer version or edits.'
while IFS= read -r path; do
  valid_path "$path" || fail "Unexpected previous path: $path"
  grep -Fq "  $path" "$backup/installed.sha256" || fail 'Backup path is outside this installation.'
  [ ! -L "$backup/files/$path" ] || fail 'Symlinks are not allowed in backup files.'
done < "$backup/previous.paths"
if [ -s "$backup/previous.sha256" ]; then
  (cd "$backup/files" && sha256sum -c "$backup/previous.sha256") >/dev/null || fail 'Prior files failed backup verification.'
fi
check_parents "$target/etc/config/luci"
work=$(mktemp -d "$target/tmp/mori-rollback.XXXXXX")
cleanup() { status=$?; trap - EXIT HUP INT TERM; case "$work" in "$target"/tmp/mori-rollback.*) rm -rf "$work" ;; esac; exit "$status"; }
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
cp -p "$target/etc/config/luci" "$work/luci.before"
config_name=mori_rollback_$$
[ ! -e "$target/tmp/.uci/$config_name" ] || fail 'Unexpected staging-package delta exists.'
mkdir "$work/config" "$work/delta"
cp "$work/luci.before" "$work/config/$config_name"
staged_uci() { uci -c "$work/config" -t "$work/delta" "$@"; }
if [ -f "$backup/previous-registration.present" ]; then
  staged_uci set "$config_name.themes.Mori=$(cat "$backup/previous-registration")"
else
  staged_uci -q delete "$config_name.themes.Mori"
fi
if [ -f "$backup/previous-media.present" ]; then
  staged_uci set "$config_name.main.mediaurlbase=$(cat "$backup/previous-media")"
else
  staged_uci -q delete "$config_name.main.mediaurlbase" || true
fi
staged_uci commit "$config_name"
[ -z "$(live_uci -q changes luci)" ] || fail 'LuCI changes appeared during rollback.'
cmp -s "$work/luci.before" "$target/etc/config/luci" || fail 'LuCI configuration changed during rollback.'
cp -p "$target/etc/config/luci" "$target/etc/config/.luci-mori-next-$$"
cat "$work/config/$config_name" > "$target/etc/config/.luci-mori-next-$$"
mv "$target/etc/config/.luci-mori-next-$$" "$target/etc/config/luci"
while read -r digest path; do
  if grep -Fxq "$path" "$backup/previous.paths"; then
    cp -p "$backup/files/$path" "$target/$path.mori-next-$$"
    mv "$target/$path.mori-next-$$" "$target/$path"
  else
    rm "$target/$path"
  fi
done < "$backup/installed.sha256"
date -Iseconds > "$backup/rolled-back"
printf 'Previous theme files and selection restored. No services restarted.\n'
printf 'Backup retained at %s\n' "$backup"

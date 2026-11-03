#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Build one native APK with the release SDK and immutable feed revisions.
set -eu
umask 022

fail() { printf '%s\n' "ERROR: $*" >&2; exit 1; }
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
out="$repo/dist/sdk"
release=25.12.0
base_url="https://downloads.immortalwrt.org/releases/$release/targets/x86/64"
sdk_name=immortalwrt-sdk-25.12.0-x86-64_gcc-14.3.0_musl.Linux-x86_64
sdk_sha=c228059aa1e58c3b3ae58ce8dcc7549fd08379d8e231daf80fcca15b677564cb
feeds_sha=505ee80d0a6e3b04b73e3f8c96d28c070bab2b54be0374fa9e59ebf510d9b130
jobs=${MORI_SDK_JOBS:-2}
case "$jobs" in ''|*[!0-9]*|0) fail 'MORI_SDK_JOBS must be a positive integer' ;; esac
for command in curl tar zstd sha256sum git make python3 openssl awk sed find; do
    command -v "$command" >/dev/null || fail "Missing dependency: $command"
done
[ "$(uname -s)" = Linux ] || fail 'The official SDK requires Linux x86_64'
[ "$(uname -m)" = x86_64 ] || fail 'The official SDK requires Linux x86_64'

# MORI_SDK_WORKDIR is a parent directory, never a directory to delete.
work_parent=${MORI_SDK_WORKDIR:-${TMPDIR:-/tmp}}
mkdir -p "$work_parent"
work_parent=$(CDPATH= cd -- "$work_parent" && pwd -P)
work=$(mktemp -d "$work_parent/mori-sdk.XXXXXXXX")
touch "$work/.mori-owned-workdir"
cleanup() {
    case "$work" in "$work_parent"/mori-sdk.*)
        [ -f "$work/.mori-owned-workdir" ] && rm -rf -- "$work"
        ;; *) printf '%s\n' 'Refusing to clean an unexpected SDK path' >&2 ;;
    esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$out"
[ -z "$(find "$out" -mindepth 1 -maxdepth 1 -print -quit)" ] || fail 'dist/sdk must be empty; move the previous artifacts before rebuilding'

download() { curl --fail --location --retry 4 --connect-timeout 30 --output "$2" "$1"; }
download "$base_url/$sdk_name.tar.zst" "$work/sdk.tar.zst"
printf '%s  %s\n' "$sdk_sha" "$work/sdk.tar.zst" | sha256sum -c -
download "$base_url/feeds.buildinfo" "$work/feeds.buildinfo"
printf '%s  %s\n' "$feeds_sha" "$work/feeds.buildinfo" | sha256sum -c -
tar --zstd -xf "$work/sdk.tar.zst" -C "$work"
sdk="$work/$sdk_name"
[ -f "$sdk/feeds.conf.default" ] || fail 'Unexpected SDK layout'

# The SDK's base feed points at its exact firmware source commit. The three
# required feeds are pinned; no branch tip is consulted during this build.
awk '$1 == "src-git" && $2 == "--root=package" && $3 == "base" { print }' "$sdk/feeds.conf.default" > "$sdk/feeds.conf"
[ "$(wc -l < "$sdk/feeds.conf")" -eq 1 ] || fail 'SDK has no unique pinned base feed'
awk '$2 == "packages" || $2 == "luci" { print }' "$work/feeds.buildinfo" >> "$sdk/feeds.conf"
python3 - "$sdk/feeds.conf" <<'PY'
import pathlib, re, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
assert len(lines) == 3, lines
assert all(re.search(r'https://[^ ]+\^[0-9a-f]{40}$', s) for s in lines), lines
PY
cp "$work/feeds.buildinfo" "$out/feeds.buildinfo"
cp "$sdk/feeds.conf" "$out/feeds.conf"
mkdir -p "$sdk/package/luci-theme-mori"
for item in Makefile LICENSE htdocs ucode root; do
    cp -R "$repo/$item" "$sdk/package/luci-theme-mori/"
done
source_commit=$(git -C "$repo" rev-parse HEAD)
source_epoch=${SOURCE_DATE_EPOCH:-$(git -C "$repo" show -s --format=%ct HEAD)}
export SOURCE_DATE_EPOCH="$source_epoch"
export TZ=UTC LC_ALL=C
(
    cd "$sdk"
    ./scripts/feeds update -a
    ./scripts/feeds install -a
    cat > .config <<'CONFIG'
CONFIG_ALL=n
CONFIG_ALL_NONSHARED=n
CONFIG_ALL_KMODS=n
CONFIG_AUTOREMOVE=n
CONFIG_SIGNED_PACKAGES=n
CONFIG_PACKAGE_luci-theme-mori=m
CONFIG_LUCI_MINIFY_JS=n
CONFIG_LUCI_MINIFY_CSS=n
CONFIG_LUCI_MINIFY_UT=n
CONFIG_LUCI_SRCDIET=n
CONFIG_LUCI_CSSTIDY=n
CONFIG_LUCI_JSMIN=n
CONFIG
    make defconfig
    # This package target may prepare its host build tools, never a firmware.
    make -j"$jobs" package/luci-theme-mori/compile V=s
)
cp "$sdk/.config" "$out/sdk.config"
find "$sdk/bin/packages" -type f -name 'luci-theme-mori-*.apk' > "$work/packages"
[ "$(wc -l < "$work/packages")" -eq 1 ] || fail 'Expected exactly one Mori APK'
package=$(cat "$work/packages")
package_name=$(basename "$package")
cp "$package" "$out/$package_name"
apk="$sdk/staging_dir/host/bin/apk"
[ -x "$apk" ] || fail 'SDK apk tool is missing'
# A per-build key verifies this artifact without changing the router's trusted
# keys. Its private half exists only in the temporary SDK work directory.
mkdir -m 700 "$work/signing" "$work/keys"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work/signing/private.pem" 2> "$work/signing/keygen.log"
chmod 600 "$work/signing/private.pem"
openssl pkey -in "$work/signing/private.pem" -pubout -out "$out/mori-sdk-signing-public.pem"
cp "$out/mori-sdk-signing-public.pem" "$work/keys/"
package="$out/$package_name"
printf '%s\n' 'Signing the locally built unsigned APK with a disposable build key'
"$apk" --allow-untrusted adbsign --sign-key "$work/signing/private.pem" "$package"
printf '%s\n' 'Verifying the signed APK with its scoped public key'
"$apk" --keys-dir "$work/keys" --no-network --repositories-file /dev/null verify "$package" > "$out/signature-verification.txt"
"$apk" --keys-dir "$work/keys" adbdump "$package" > "$out/package-metadata.yaml"
mkdir -p "$work/payload" "$out/hooks"
"$apk" --keys-dir "$work/keys" extract --no-chown --destination "$work/payload" "$package"
hook_dir=$(find "$sdk/build_dir" -type d -path '*/apk-all/luci-theme-mori' -print)
[ -n "$hook_dir" ] && [ -d "$hook_dir" ] || fail 'Expected one generated APK hooks directory'
find "$hook_dir" -maxdepth 1 -type f -exec cp '{}' "$out/hooks/" \;
python3 "$repo/scripts/inspect-apk.py" "$repo" "$work/payload" "$out"
python3 - "$repo" "$sdk" "$out" "$source_commit" "$source_epoch" "$base_url/$sdk_name.tar.zst" "$sdk_sha" "$feeds_sha" "$package_name" <<'PY'
import hashlib, json, pathlib, subprocess, sys
repo, sdk, out = map(pathlib.Path, sys.argv[1:4])
commit, epoch, url, sdk_sha, feeds_sha, package = sys.argv[4:]
feeds = {}
for name in ('base', 'packages', 'luci'):
    feeds[name] = subprocess.check_output(['git', '-C', str(sdk/'feeds'/name), 'rev-parse', 'HEAD'], text=True).strip()
dirty = bool(subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip())
data = dict(package=package, source_commit=commit, source_dirty=dirty, source_date_epoch=int(epoch),
            sdk_url=url, sdk_sha256=sdk_sha, feeds_buildinfo_sha256=feeds_sha, feeds=feeds,
            target='x86/64', architecture='noarch', signing='ephemeral RSA-2048 build key',
            public_key_sha256=hashlib.sha256((out/'mori-sdk-signing-public.pem').read_bytes()).hexdigest(),
            build_target='package/luci-theme-mori/compile', payload_matches_source=True)
(out/'provenance.json').write_text(json.dumps(data, indent=2)+'\n')
PY
(
    cd "$out"
    sha256sum "$package_name" mori-sdk-signing-public.pem > APK-SHA256SUMS
    find . -type f ! -name SHA256SUMS -print | LC_ALL=C sort | while IFS= read -r file; do sha256sum "${file#./}"; done > SHA256SUMS
)
printf '\nNative APK and public audit files: %s\n' "$out"

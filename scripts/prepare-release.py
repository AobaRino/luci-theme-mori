#!/usr/bin/env python3
"""Assemble only verified CI outputs into the seven public release assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SMOKE_PASSES = (
    'PASS: native APK install, registration, payload and template compilation',
    'PASS: generated post-upgrade hook preserves active Mori',
    'PASS: pending LuCI drafts preserved and explicit removal refused',
    'PASS: missing fallback leaves active Mori untouched',
    'PASS: native uninstall, usable fallback, unchanged non-LuCI configuration and pending network edits',
)
SDK_FILES = {
    'APK-SHA256SUMS', 'feeds.buildinfo', 'feeds.conf', 'sdk.config',
    'mori-sdk-signing-public.pem', 'native-smoke-test.txt', 'package-metadata.yaml',
    'payload-sha256.txt', 'payload-verification.txt', 'provenance.json',
    'signature-verification.txt', 'hooks/post-install', 'hooks/post-upgrade',
    'hooks/postinst-pkg', 'hooks/postrm', 'hooks/pre-deinstall', 'hooks/prerm-pkg',
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> bool:
    return bool(name and not name.startswith('/') and '\\' not in name
                and ':' not in name and all(ord(c) >= 32 for c in name)
                and all(part not in ('', '.', '..') for part in name.split('/')))


def parse_sums(text: str, *, absolute: bool = False) -> dict[str, str]:
    sums = {}
    for line in text.splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        require(match is not None, 'Malformed checksum line')
        checksum, name = match.groups()
        if absolute:
            require(name.startswith('/'), 'Payload checksum paths must be absolute')
            name = name[1:]
        require(safe_name(name), f'Unsafe checksum path: {name!r}')
        require(name not in sums, f'Duplicate checksum path: {name}')
        sums[name] = checksum
    require(bool(sums), 'Empty checksum manifest')
    return sums


def regular_files(directory: Path) -> dict[str, Path]:
    require(directory.is_dir() and not directory.is_symlink(), f'Invalid input directory: {directory}')
    files = {}
    for path in directory.rglob('*'):
        require(not path.is_symlink(), f'Symlink in artifact: {path}')
        require(path.is_dir() or path.is_file(), f'Non-regular artifact entry: {path}')
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            require(safe_name(name), f'Unsafe artifact path: {name}')
            files[name] = path
    return files


def release_identity(root: Path, tag: str, commit: str) -> dict:
    require(bool(re.fullmatch(r'v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', tag)),
            'Release tags must use stable vX.Y.Z format')
    require(bool(re.fullmatch(r'[0-9a-f]{40}', commit)), 'Commit must be a full lowercase SHA')
    version = (root / 'VERSION').read_text(encoding='ascii').strip()
    makefile = (root / 'Makefile').read_text(encoding='utf-8')
    versions = re.findall(r'^PKG_VERSION:=(\S+)\s*$', makefile, re.M)
    releases = re.findall(r'^PKG_RELEASE:=(\S+)\s*$', makefile, re.M)
    require(version == tag[1:] and versions == [version], 'Tag, VERSION and Makefile PKG_VERSION must match')
    require(len(releases) == 1 and bool(re.fullmatch(r'[1-9]\d*', releases[0])),
            'Makefile must have one positive PKG_RELEASE')
    return dict(tag=tag, commit=commit, version=version, package_release=releases[0],
                package=f'luci-theme-mori-{version}-r{releases[0]}.apk')


def check_sdk(sdk: Path, identity: dict) -> tuple[dict[str, Path], dict[str, str]]:
    files = regular_files(sdk)
    expected = SDK_FILES | {identity['package'], 'SHA256SUMS'}
    require(set(files) == expected, 'Unexpected or missing SDK artifact files')
    sums = parse_sums(files['SHA256SUMS'].read_text(encoding='ascii'))
    require(set(sums) == expected - {'SHA256SUMS'}, 'SDK checksum manifest must cover every artifact exactly')
    for name, checksum in sums.items():
        require(digest(files[name].read_bytes()) == checksum, f'SDK checksum mismatch: {name}')
    apk_sums = parse_sums(files['APK-SHA256SUMS'].read_text(encoding='ascii'))
    require(set(apk_sums) == {identity['package'], 'mori-sdk-signing-public.pem'},
            'APK-SHA256SUMS must contain only the expected APK and public key')
    require(all(sums[name] == checksum for name, checksum in apk_sums.items()), 'APK checksum manifest disagrees with SDK manifest')
    provenance = json.loads(files['provenance.json'].read_text(encoding='utf-8'))
    require(provenance.get('source_commit') == identity['commit'], 'SDK provenance commit differs from release commit')
    require(provenance.get('source_dirty') is False, 'SDK must be built from a clean checkout')
    require(provenance.get('package') == identity['package'] and provenance.get('architecture') == 'noarch'
            and provenance.get('payload_matches_source') is True, 'SDK provenance package identity or payload audit failed')
    require(provenance.get('public_key_sha256') == sums['mori-sdk-signing-public.pem'], 'Provenance public key differs from the artifact')
    metadata = files['package-metadata.yaml'].read_text(encoding='utf-8')
    for key, value in (('name', 'luci-theme-mori'), ('version', f"{identity['version']}-r{identity['package_release']}"), ('arch', 'noarch')):
        require(bool(re.search(rf'^  {key}: {re.escape(value)}$', metadata, re.M)), f'Unexpected APK metadata: {key}')
    signature = files['signature-verification.txt'].read_text(encoding='utf-8').strip()
    require(signature.endswith(identity['package'] + ': OK'), 'Missing successful APK signature verification')
    payload_audit = files['payload-verification.txt'].read_text(encoding='utf-8')
    require(bool(re.search(r'^PASS: [1-9]\d* source files preserved byte-for-byte\.$', payload_audit, re.M))
            and 'PASS: only the SDK package file list is added.' in payload_audit
            and 'PASS: package identity, noarch architecture, dependencies and hooks checked.' in payload_audit,
            'Missing successful SDK payload audit')
    smoke = files['native-smoke-test.txt'].read_text(encoding='utf-8').splitlines()
    require(all(line in smoke for line in SMOKE_PASSES) and not any(line.startswith('FAIL:') for line in smoke),
            'Missing successful native installation smoke tests')
    payload = parse_sums(files['payload-sha256.txt'].read_text(encoding='ascii'), absolute=True)
    return files, payload


def check_standalone(dist: Path, identity: dict, native_payload: dict[str, str]) -> tuple[Path, Path]:
    name = f"luci-theme-mori-{identity['version']}"
    archive, checksums = dist / (name + '.tar.gz'), dist / (name + '.tar.gz.sha256')
    require(archive.is_file() and not archive.is_symlink() and checksums.is_file() and not checksums.is_symlink(),
            'Missing regular standalone archive or checksum file')
    sums = parse_sums(checksums.read_text(encoding='ascii'))
    require(sums == {archive.name: digest(archive.read_bytes())}, 'Standalone archive checksum mismatch')
    with tarfile.open(archive, 'r:gz') as tar:
        entries = tar.getmembers()
        names = [item.name for item in entries]
        prefix = name + '/'
        require(len(names) == len(set(names)), 'Duplicate standalone archive entry')
        require(all(item.isfile() and safe_name(item.name) and item.name.startswith(prefix) for item in entries),
                'Unsafe standalone archive entry')
        contents = {item.name[len(prefix):]: tar.extractfile(item).read() for item in entries}
    require(contents.get('VERSION', b'').decode('ascii').strip() == identity['version'], 'Standalone archive version differs from tag')
    require('manifest.sha256' in contents and 'scripts/install.sh' in contents and 'scripts/rollback.sh' in contents,
            'Incomplete standalone installer')
    manifest = parse_sums(contents['manifest.sha256'].decode('ascii'))
    payload = {name[7:]: digest(data) for name, data in contents.items() if name.startswith('rootfs/')}
    require(payload == manifest, 'Standalone payload manifest mismatch')
    native_theme = {name: checksum for name, checksum in native_payload.items()
                    if name not in {'usr/libexec/mori-register', 'lib/apk/packages/luci-theme-mori.list'}}
    require(payload == native_theme, 'Standalone and SDK theme payloads differ')
    return archive, checksums


def prepare(root: Path, tag: str, commit: str) -> dict:
    identity = release_identity(root, tag, commit)
    dist = root / 'dist'
    files, native_payload = check_sdk(dist / 'sdk', identity)
    archive, checksums = check_standalone(dist, identity, native_payload)
    output, metadata = dist / 'release', dist / 'release-metadata'
    for directory in (output, metadata):
        require(not directory.is_symlink() and not directory.exists(), f'Release output already exists: {directory}')
    output.mkdir()
    metadata.mkdir()
    for path in (files[identity['package']], files['mori-sdk-signing-public.pem'], files['APK-SHA256SUMS'], archive, checksums):
        shutil.copyfile(path, output / path.name)
    bundle = output / f"luci-theme-mori-{identity['version']}-sdk-verification.zip"
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for name, path in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            zip_file.writestr(info, path.read_bytes())
    (output / (bundle.name + '.sha256')).write_text(f'{digest(bundle.read_bytes())}  {bundle.name}\n', encoding='ascii', newline='\n')
    manifest = dict(identity, assets=[dict(name=path.name, sha256=digest(path.read_bytes()), size=path.stat().st_size)
                                     for path in sorted(output.iterdir())])
    (metadata / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    notes = f"""Mori {tag}：适用于 ImmortalWrt 的 LuCI 主题。

基于源码提交 `{commit}`，使用固定的 ImmortalWrt 25.12.0 x86/64 SDK 和 feeds 构建。
源码检查、独立安装器测试、APK 签名与文件审计、隔离环境安装和卸载测试均已通过；同时验证了生成的升级脚本和配置草稿保护。

原生安装请同时下载 `{identity['package']}`、`mori-sdk-signing-public.pem` 和 `APK-SHA256SUMS`，按[安装说明](https://github.com/AobaRino/luci-theme-mori/blob/{tag}/docs/INSTALL.md)校验，并使用临时公钥目录安装。

同时提供独立 `.tar.gz` 安装包及校验文件。SDK 验证 ZIP 包含构建来源、软件包元数据、生成脚本、签名校验及原生测试日志。

自动化原生测试使用隔离的官方 rootfs；发布流程不会连接或安装到实际路由器。包的 `noarch` 标识不代表其他固件版本或架构已通过验收。本流程不构建旧版 `.ipk`。
"""
    (metadata / 'release-notes.md').write_text(notes, encoding='utf-8', newline='\n')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        result = release_identity(ROOT, args.tag, args.commit) if args.check_only else prepare(ROOT, args.tag, args.commit)
    except (ValueError, OSError, tarfile.TarError) as error:
        parser.exit(1, f'Release validation failed: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

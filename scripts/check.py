#!/usr/bin/env python3
"""Check source hygiene, asset references and the standalone archive manifest."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import shutil
import sys
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


def main():
    version = (ROOT / 'VERSION').read_text().strip()
    require(f'PKG_VERSION:={version}' in (ROOT / 'Makefile').read_text(), 'Makefile PKG_VERSION and VERSION differ')
    static = ROOT / 'htdocs/luci-static/mori'
    templates = ROOT / 'ucode/template/themes/mori'
    for folder in [ROOT / 'htdocs', ROOT / 'ucode', ROOT / 'root', ROOT / 'scripts']:
        for path in folder.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix in ['.woff', '.woff2', '.png']:
                continue
            content = path.read_bytes().decode('utf-8')
            require('\r' not in content, f'CRLF in {path.relative_to(ROOT)}')
            if path.suffix in ['.ut', '.js', '.css']:
                require('@MORI_VERSION@' not in content, f'Unbuilt template: {path.name}')
                require('Immortal Modern' not in content, f'Old display name: {path.name}')
                require("L.require('menu-argon')" not in content, f'External Argon menu dependency: {path.name}')
            # Deployment helpers and live evidence must remain outside the public repo.
            require(not re.search(r'(?<![\w.])(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?![\w.])', content), f'Private address in {path.relative_to(ROOT)}')
            require(not re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----', content), f'Private key in {path.relative_to(ROOT)}')

    for css in static.rglob('*.css'):
        for ref in re.findall(r'url\(([^)]+)\)', css.read_text(encoding='utf-8')):
            ref = ref.strip().strip('\"\'')
            if ref.startswith(('data:', '/', 'http:', 'https:')):
                continue
            require((css.parent / ref.split('?')[0]).is_file(), f'Missing CSS asset: {css.name}: {ref}')
    ET.parse(static / 'icon.svg')
    manifest = json.loads((static / 'manifest.webmanifest').read_text(encoding='utf-8'))
    require(manifest['name'].startswith('Mori'), 'Manifest name must be Mori')
    for template in templates.glob('*.ut'):
        text = template.read_text(encoding='utf-8')
        for ref, fingerprint in re.findall(r'\{\{ media \}\}/([^"? ]+)\?v=([a-f0-9]+)', text):
            path = static / ref
            require(path.is_file(), f'Missing template asset: {ref}')
            if path.is_file():
                require(hashlib.sha256(path.read_bytes()).hexdigest().startswith(fingerprint), f'Stale asset fingerprint: {template.name}: {ref}; run build.py')
    node = shutil.which('node')
    if node:
        for script in (ROOT / 'htdocs').rglob('*.js'):
            result = subprocess.run([node, '--check', str(script)], capture_output=True, text=True)
            require(result.returncode == 0, f'JavaScript syntax: {script.name}: {result.stderr.strip()}')
    else:
        print('Note: Node.js unavailable; JavaScript syntax check skipped.')

    archive = ROOT / 'dist' / f'luci-theme-mori-{version}.tar.gz'
    require(archive.is_file(), 'Missing distribution; run scripts/build.py first')
    if archive.is_file():
        with tarfile.open(archive, 'r:gz') as tar:
            members = {m.name: m for m in tar.getmembers()}
            prefix = f'luci-theme-mori-{version}/'
            for name, item in members.items():
                require(name.startswith(prefix) and '..' not in Path(name).parts and item.isfile(), f'Unsafe archive member: {name}')
            sums = tar.extractfile(prefix + 'manifest.sha256').read().decode('ascii').splitlines()
            paths = set()
            for line in sums:
                expected, relative = line.split('  ', 1)
                paths.add(prefix + 'rootfs/' + relative)
                actual = hashlib.sha256(tar.extractfile(prefix + 'rootfs/' + relative).read()).hexdigest()
                require(expected == actual, f'Archive checksum mismatch: {relative}')
            require(paths == {name for name in members if name.startswith(prefix + 'rootfs/')}, 'Manifest does not exactly cover rootfs')
        print(f'Archive verified: {len(paths)} payload files')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        raise SystemExit(1)
    print('Source, asset references, fingerprints and archive checks passed.')


if __name__ == '__main__':
    main()

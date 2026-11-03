#!/usr/bin/env python3
"""Build a deterministic standalone Mori archive with only publishable files.

Refresh source template asset fingerprints first, so SDK packages built directly
from the repository use the same assets and cache keys as the standalone archive.
"""
from pathlib import Path
import gzip
import hashlib
import io
import re
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    version = (ROOT / 'VERSION').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.]+)?', version):
        raise SystemExit('Invalid VERSION')
    static = ROOT / 'htdocs/luci-static/mori'
    templates = ROOT / 'ucode/template/themes/mori'
    for template in sorted(templates.glob('*.ut')):
        original = template.read_text(encoding='utf-8')
        text = original.replace('@MORI_VERSION@', version)
        text = re.sub(r'Mori \d+\.\d+\.\d+(?:-[a-z0-9.]+)? ·', f'Mori {version} ·', text)
        for asset in ['css/cascade.css', 'css/dark.css', 'mori.css', 'theme.js', 'icon.svg']:
            text = re.sub(re.escape(asset) + r'\?v=[a-zA-Z0-9_.-]+', asset + '?v=' + digest(static / asset)[:12], text)
        if text != original:
            template.write_text(text, encoding='utf-8', newline='\n')

    required = ['scripts/install.sh', 'scripts/rollback.sh', 'README.md', 'LICENSE',
                'THIRD_PARTY_NOTICES.md', 'docs/INSTALL.md', 'docs/DEVELOPMENT.md',
                'docs/VALIDATION.md']
    for name in required:
        if not (ROOT / name).is_file():
            raise SystemExit(f'Missing distribution input: {name}')

    # Work only in the versioned distribution folder owned by this build.
    dist = ROOT / 'dist'
    output = dist / ('luci-theme-mori-' + version)
    if output.exists():
        if output.resolve().parent != dist.resolve():
            raise SystemExit('Refusing to replace a path outside dist/')
        shutil.rmtree(output)
    output.mkdir(parents=True)
    rootfs = output / 'rootfs'
    shutil.copytree(ROOT / 'htdocs', rootfs / 'www')
    shutil.copytree(ROOT / 'ucode', rootfs / 'usr/share/ucode/luci')
    for name in required + ['VERSION']:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    for path in sorted((ROOT / 'docs/images').glob('*.jpg')):
        target = output / 'docs/images' / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    files = sorted(p for p in rootfs.rglob('*') if p.is_file())
    manifest = ''.join(f'{digest(path)}  {path.relative_to(rootfs).as_posix()}\n' for path in files)
    (output / 'manifest.sha256').write_bytes(manifest.encode('ascii'))

    archive = dist / (output.name + '.tar.gz')
    with archive.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as tar:
                for path in sorted(p for p in output.rglob('*') if p.is_file()):
                    data = path.read_bytes()
                    info = tarfile.TarInfo(output.name + '/' + path.relative_to(output).as_posix())
                    info.size = len(data)
                    info.mode = 0o755 if path.suffix == '.sh' else 0o644
                    info.mtime = 0
                    tar.addfile(info, io.BytesIO(data))
    (dist / (archive.name + '.sha256')).write_text(f'{digest(archive)}  {archive.name}\n', encoding='ascii', newline='\n')
    print(f'Built {archive.name}: {len(files)} payload files, {archive.stat().st_size} bytes')


if __name__ == '__main__':
    build()

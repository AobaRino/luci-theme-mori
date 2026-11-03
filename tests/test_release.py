"""Release assembly rejects mismatched versions, provenance and tampered artifacts."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_release', PROJECT / 'scripts/prepare-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
COMMIT = '1234567890abcdef1234567890abcdef12345678'
TAG = 'v1.2.3'
PACKAGE = 'luci-theme-mori-1.2.3-r2.apk'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mori-release-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / 'dist/sdk'
        write(self.root / 'VERSION', '1.2.3\n')
        write(self.root / 'Makefile', 'PKG_VERSION:=1.2.3\nPKG_RELEASE:=2\n')
        self.theme = {'www/luci-static/mori/mori.css': b'body { color: green; }\n'}
        for name in release.SDK_FILES | {PACKAGE}:
            write(self.sdk / name, 'fixture\n')
        write(self.sdk / 'mori-sdk-signing-public.pem', 'public-key-fixture\n')
        write(self.sdk / 'APK-SHA256SUMS', ''.join(
            f'{sha((self.sdk / name).read_bytes())}  {name}\n' for name in (PACKAGE, 'mori-sdk-signing-public.pem')))
        self.provenance = dict(package=PACKAGE, source_commit=COMMIT, source_dirty=False,
                               architecture='noarch', payload_matches_source=True,
                               public_key_sha256=sha((self.sdk / 'mori-sdk-signing-public.pem').read_bytes()))
        self.save_provenance()
        write(self.sdk / 'package-metadata.yaml', 'info:\n  name: luci-theme-mori\n  version: 1.2.3-r2\n  arch: noarch\n')
        write(self.sdk / 'signature-verification.txt', f'/tmp/sdk/{PACKAGE}: OK\n')
        write(self.sdk / 'payload-verification.txt', 'PASS: 2 source files preserved byte-for-byte.\n'
              'PASS: only the SDK package file list is added.\n'
              'PASS: package identity, noarch architecture, dependencies and hooks checked.\n')
        write(self.sdk / 'native-smoke-test.txt', '\n'.join(release.SMOKE_PASSES) + '\n')
        payload = dict(self.theme, **{'usr/libexec/mori-register': b'helper', 'lib/apk/packages/luci-theme-mori.list': b'list'})
        write(self.sdk / 'payload-sha256.txt', ''.join(f'{sha(data)}  /{name}\n' for name, data in sorted(payload.items())))
        self.refresh_sdk_sums()
        self.archive = self.root / 'dist/luci-theme-mori-1.2.3.tar.gz'
        self.make_standalone()

    def save_provenance(self):
        write(self.sdk / 'provenance.json', json.dumps(self.provenance))

    def refresh_sdk_sums(self):
        files = sorted(path for path in self.sdk.rglob('*') if path.is_file() and path.name != 'SHA256SUMS')
        write(self.sdk / 'SHA256SUMS', ''.join(f'{sha(path.read_bytes())}  {path.relative_to(self.sdk).as_posix()}\n' for path in files))

    def make_standalone(self, *, payload=None, extra=None):
        payload = self.theme if payload is None else payload
        contents = {'VERSION': b'1.2.3\n', 'scripts/install.sh': b'install', 'scripts/rollback.sh': b'rollback',
                    'manifest.sha256': ''.join(f'{sha(data)}  {name}\n' for name, data in sorted(payload.items())).encode()}
        contents.update({'rootfs/' + name: data for name, data in payload.items()})
        with tarfile.open(self.archive, 'w:gz') as tar:
            for name, data in contents.items():
                item = tarfile.TarInfo('luci-theme-mori-1.2.3/' + name)
                item.size = len(data)
                tar.addfile(item, io.BytesIO(data))
            if extra:
                item = tarfile.TarInfo(extra)
                tar.addfile(item, io.BytesIO(b''))
        write(self.archive.with_name(self.archive.name + '.sha256'), f'{sha(self.archive.read_bytes())}  {self.archive.name}\n')

    def prepare(self):
        return release.prepare(self.root, TAG, COMMIT)

    def test_tag_version_and_package_release_must_match(self):
        for tag in ('v1.2.4', '1.2.3', 'v1.2.3-rc.1', 'v01.2.3'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.release_identity(self.root, tag, COMMIT)
        write(self.root / 'Makefile', 'PKG_VERSION:=1.2.3\nPKG_RELEASE:=0\n')
        with self.assertRaisesRegex(ValueError, 'positive PKG_RELEASE'):
            release.release_identity(self.root, TAG, COMMIT)

    def test_tampered_apk_is_rejected_before_output_creation(self):
        write(self.sdk / PACKAGE, 'tampered\n')
        with self.assertRaisesRegex(ValueError, 'SDK checksum mismatch'):
            self.prepare()
        self.assertFalse((self.root / 'dist/release').exists())

    def test_manifest_rejects_traversal_and_duplicate_paths(self):
        for content in (f'{"a" * 64}  ../outside\n', f'{"a" * 64}  /outside\n',
                        f'{"a" * 64}  hooks\\outside\n', f'{"a" * 64}  x\n' * 2):
            with self.subTest(content=content), self.assertRaises(ValueError):
                release.parse_sums(content)
        text = (self.sdk / 'SHA256SUMS').read_text()
        write(self.sdk / 'SHA256SUMS', text + f'{"a" * 64}  ../outside\n')
        with self.assertRaisesRegex(ValueError, 'Unsafe checksum path'):
            self.prepare()

    def test_sdk_manifest_requires_exact_coverage(self):
        lines = (self.sdk / 'SHA256SUMS').read_text().splitlines()
        write(self.sdk / 'SHA256SUMS', '\n'.join(lines[1:]) + '\n')
        with self.assertRaisesRegex(ValueError, 'cover every artifact'):
            self.prepare()

    def test_wrong_commit_or_dirty_source_is_rejected(self):
        for field, value, error in (('source_commit', '0' * 40, 'provenance commit'),
                                    ('source_dirty', True, 'clean checkout')):
            old = self.provenance[field]
            self.provenance[field] = value
            self.save_provenance()
            self.refresh_sdk_sums()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                self.prepare()
            self.provenance[field] = old

    def test_failed_or_incomplete_native_smoke_is_rejected(self):
        write(self.sdk / 'native-smoke-test.txt', '\n'.join(release.SMOKE_PASSES[:-1]))
        self.refresh_sdk_sums()
        with self.assertRaisesRegex(ValueError, 'native installation smoke'):
            self.prepare()

    def test_different_standalone_payload_is_rejected_even_with_valid_checksums(self):
        self.make_standalone(payload={'www/luci-static/mori/mori.css': b'different theme'})
        with self.assertRaisesRegex(ValueError, 'Standalone and SDK theme payloads differ'):
            self.prepare()

    def test_unsafe_archive_entry_is_rejected(self):
        self.make_standalone(extra='luci-theme-mori-1.2.3/../../outside')
        with self.assertRaisesRegex(ValueError, 'Unsafe standalone archive entry'):
            self.prepare()

    def test_seven_assets_are_complete_and_preserve_tested_bytes(self):
        manifest = self.prepare()
        output = self.root / 'dist/release'
        self.assertEqual(len(manifest['assets']), 7)
        self.assertEqual(manifest['tag'], TAG)
        self.assertEqual(manifest['commit'], COMMIT)
        self.assertEqual({entry['name'] for entry in manifest['assets']}, {path.name for path in output.iterdir()})
        for entry in manifest['assets']:
            data = (output / entry['name']).read_bytes()
            self.assertEqual(entry['sha256'], sha(data))
            self.assertEqual(entry['size'], len(data))
        self.assertEqual((output / PACKAGE).read_bytes(), (self.sdk / PACKAGE).read_bytes())
        self.assertEqual((output / self.archive.name).read_bytes(), self.archive.read_bytes())
        with zipfile.ZipFile(output / 'luci-theme-mori-1.2.3-sdk-verification.zip') as bundle:
            files = release.regular_files(self.sdk)
            self.assertEqual(set(bundle.namelist()), set(files))
            for name, path in files.items():
                self.assertEqual(bundle.read(name), path.read_bytes())
        stored = json.loads((self.root / 'dist/release-metadata/release-manifest.json').read_text())
        self.assertEqual(stored, manifest)
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            self.prepare()


if __name__ == '__main__':
    unittest.main()

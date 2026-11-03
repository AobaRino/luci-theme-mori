"""Integration tests for release validation, file rollback and config guards.

Run with Python's standard unittest runner. Requires a POSIX shell (Git Bash
is supported on Windows). All paths and router commands are isolated fixtures.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SHELL = os.environ.get("MORI_TEST_SHELL") or shutil.which("sh")
if not SHELL and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    if candidate.is_file():
        SHELL = str(candidate)


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


@unittest.skipUnless(SHELL, "A POSIX shell is required")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mori-installer-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "router"
        self.release = self.base / "release"
        self.bin = self.base / "bin"
        write(self.root / ".mori-test-root", "fixture\n")
        write(self.root / "usr/share/ucode/luci/runtime.uc", "// fixture\n")
        write(self.root / "usr/share/ucode/luci/template/themes/bootstrap/header.ut", "<html>\n")
        write(self.root / "www/luci-static/bootstrap/base.css", "body {}\n")
        self.original = {"themes": "internal", "themes.Bootstrap": "/luci-static/bootstrap", "main.mediaurlbase": "/luci-static/bootstrap", "main.lang": "zh_cn"}
        write(self.root / "etc/config/luci", json.dumps(self.original, sort_keys=True))
        write(self.root / "etc/config/network", "network-config-must-not-change\n")
        self.network = (self.root / "etc/config/network").read_bytes()
        for filename in ("install.sh", "rollback.sh"):
            write(self.release / "scripts" / filename, (PROJECT / "scripts" / filename).read_text())
        write(self.release / "VERSION", "0.1.0\n")
        self.files = {
            "www/luci-static/mori/mori.css": "body { color: green; }\n",
            "www/luci-static/mori/theme.js": "/* Mori */\n",
            "www/luci-static/resources/menu-mori.js": "/* menu */\n",
        }
        for name in ("header", "header_login", "footer", "footer_login", "sysauth", "out_header_login"):
            self.files[f"usr/share/ucode/luci/template/themes/mori/{name}.ut"] = "<div>Mori</div>\n"
        for path, content in self.files.items():
            write(self.release / "rootfs" / path, content)
        self.manifest()
        mock = PROJECT / "tests/mock_router_commands.py"
        for command in ("uci", "ucode"):
            write(self.bin / command, f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{mock.as_posix()}" {command} "$@"\n')
            (self.bin / command).chmod(0o755)
        self.env = dict(os.environ, MORI_TEST_ROOT=self.root.as_posix(), MSYS2_ARG_CONV_EXCL="*")
        self.env["PATH"] = str(self.bin) + os.pathsep + os.environ.get("PATH", "")
        # Bash converts a Windows PATH, and discovers the fixture wrappers.

    def manifest(self):
        content = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(self.release / 'rootfs').as_posix()}\n" for path in sorted((self.release / "rootfs").rglob("*")) if path.is_file())
        write(self.release / "manifest.sha256", content)

    def run_script(self, script, *args, success=True):
        result = subprocess.run([SHELL, str(script), *args], env=self.env, text=True, encoding="utf-8", errors="replace", capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "etc/config/network").read_bytes(), self.network)
        return result

    def install(self, activate=False, success=True):
        result = self.run_script(self.release / "scripts/install.sh", *(("--activate",) if activate else ()), success=success)
        backups = self.root / "root/mori-backups"
        completed = sorted(p for p in backups.glob("*") if (p / "complete").exists()) if backups.exists() else []
        return completed[-1] if completed else None, result

    def config(self):
        return json.loads((self.root / "etc/config/luci").read_text())

    def set_config(self, key, value):
        data = self.config()
        data[key] = value
        write(self.root / "etc/config/luci", json.dumps(data, sort_keys=True))

    def test_registration_does_not_activate_and_rollback_preserves_other_settings(self):
        backup, _ = self.install()
        self.assertEqual(self.config()["main.mediaurlbase"], "/luci-static/bootstrap")
        self.assertEqual(self.config()["themes.Mori"], "/luci-static/mori")
        if os.name != "nt":
            self.assertEqual((self.root / "www/luci-static/mori").stat().st_mode & 0o777, 0o755)
            self.assertEqual((self.root / "www/luci-static/mori/theme.js").stat().st_mode & 0o777, 0o644)
        self.set_config("main.lang", "en")
        self.run_script(backup / "rollback.sh")
        self.assertNotIn("themes.Mori", self.config())
        self.assertEqual(self.config()["main.lang"], "en")
        self.assertFalse((self.root / "www/luci-static/mori/theme.js").exists())
        self.run_script(backup / "rollback.sh")

    def test_activation_and_upgrade_restore_prior_files(self):
        first, _ = self.install(activate=True)
        self.assertEqual(self.config()["main.mediaurlbase"], "/luci-static/mori")
        write(self.release / "rootfs/www/luci-static/mori/theme.js", "/* Mori updated */\n")
        self.manifest()
        second, _ = self.install(activate=True)
        self.run_script(first / "rollback.sh", success=False)
        self.run_script(second / "rollback.sh")
        self.assertEqual((self.root / "www/luci-static/mori/theme.js").read_text(), self.files["www/luci-static/mori/theme.js"])
        self.run_script(first / "rollback.sh")
        self.assertEqual(self.config()["main.mediaurlbase"], "/luci-static/bootstrap")

    def test_corrupt_payload_and_extra_file_are_rejected_before_writes(self):
        write(self.release / "rootfs/www/luci-static/mori/theme.js", "changed")
        _, result = self.install(success=False)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertEqual(self.config(), self.original)
        self.assertFalse((self.root / "www/luci-static/mori").exists())
        self.manifest()
        write(self.release / "rootfs/www/luci-static/mori/extra.js", "extra")
        _, result = self.install(success=False)
        self.assertIn("manifest differ", result.stderr)
        self.assertFalse((self.root / "www/luci-static/mori").exists())

    def test_unsafe_manifest_and_bad_template_are_rejected(self):
        with (self.release / "manifest.sha256").open("a") as out:
            out.write("0" * 64 + "  ../../etc/config/network\n")
        _, result = self.install(success=False)
        self.assertIn("Unexpected release path", result.stderr)
        self.manifest()
        write(self.release / "rootfs/usr/share/ucode/luci/template/themes/mori/header.ut", "INVALID_TEMPLATE")
        self.manifest()
        _, result = self.install(success=False)
        self.assertIn("Template compilation failed", result.stderr)
        self.assertEqual(self.config(), self.original)

    def test_existing_drafts_are_preserved(self):
        write(self.root / "pending", "luci.main.lang='en'\n")
        _, result = self.install(success=False)
        self.assertIn("uncommitted changes", result.stderr)
        self.assertEqual(self.config(), self.original)
        self.assertEqual((self.root / "pending").read_text(), "luci.main.lang='en'\n")

    def test_draft_arriving_during_install_restores_copied_files(self):
        write(self.root / "inject-pending-after", "2")
        _, result = self.install(success=False)
        self.assertIn("changes appeared during installation", result.stderr)
        self.assertEqual(self.config(), self.original)
        self.assertFalse((self.root / "www/luci-static/mori/theme.js").exists())
        self.assertTrue((self.root / "pending").exists())

    def test_rollback_refuses_new_theme_choice_or_modified_assets(self):
        backup, _ = self.install(activate=True)
        self.set_config("main.mediaurlbase", "/luci-static/bootstrap")
        self.run_script(backup / "rollback.sh", success=False)
        self.assertEqual(self.config()["main.mediaurlbase"], "/luci-static/bootstrap")
        self.set_config("main.mediaurlbase", "/luci-static/mori")
        write(self.root / "www/luci-static/mori/theme.js", "user edit")
        self.run_script(backup / "rollback.sh", success=False)
        self.assertEqual((self.root / "www/luci-static/mori/theme.js").read_text(), "user edit")

    def test_repeat_install_is_idempotent_and_package_overlap_refused(self):
        first, _ = self.install()
        expected = self.config()
        self.install()
        self.assertEqual(self.config(), expected)
        write(self.root / "usr/lib/opkg/info/luci-theme-mori.control", "Package: luci-theme-mori\n")
        self.install(success=False)
        self.run_script(first / "rollback.sh", success=False)


if __name__ == "__main__":
    unittest.main()

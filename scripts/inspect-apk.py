#!/usr/bin/env python3
"""Validate an SDK-extracted APK against the committed source payload."""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys


def main() -> None:
    repo, payload, output = (pathlib.Path(value) for value in sys.argv[1:])
    expected: dict[str, pathlib.Path] = {}
    for source, destination in (("htdocs", "www"), ("ucode", "usr/share/ucode/luci"), ("root", "")):
        for path in (repo / source).rglob("*"):
            if path.is_symlink():
                raise SystemExit(f"Unexpected source symlink: {path}")
            if path.is_file():
                relative = (pathlib.PurePosixPath(destination) / path.relative_to(repo / source).as_posix()).as_posix()
                expected[relative] = path
    actual = {path.relative_to(payload).as_posix(): path for path in payload.rglob("*") if path.is_file() or path.is_symlink()}
    framework_files = {"lib/apk/packages/luci-theme-mori.list"}
    assert set(actual) == set(expected) | framework_files, {
        "missing": sorted(set(expected) - set(actual)),
        "unexpected": sorted(set(actual) - set(expected) - framework_files),
    }
    for name, source in expected.items():
        assert not actual[name].is_symlink(), f"Unexpected payload symlink: {name}"
        assert source.read_bytes() == actual[name].read_bytes(), f"Payload differs from source: {name}"
    metadata = (output / "package-metadata.yaml").read_text()
    makefile = (repo / "Makefile").read_text()
    version = re.search(r"^PKG_VERSION:=(.+)$", makefile, re.M).group(1)
    release = re.search(r"^PKG_RELEASE:=(.+)$", makefile, re.M).group(1)
    for key, value in (("name", "luci-theme-mori"), ("version", f"{version}-r{release}"), ("arch", "noarch")):
        assert re.search(rf"^\s*{key}:\s*['\"]?{re.escape(value)}['\"]?\s*$", metadata, re.M), (key, value)
    for dependency in ("luci-base", "ucode", "ucode-mod-uci", "ucode-mod-fs"):
        assert dependency in metadata, f"Missing dependency: {dependency}"
    for hook in ("post-install", "post-upgrade", "pre-deinstall", "postrm"):
        assert (output / "hooks" / hook).is_file(), f"Missing generated hook: {hook}"
    listing = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  /{name}\n" for name, path in sorted(actual.items()))
    (output / "payload-sha256.txt").write_text(listing)
    (output / "payload-verification.txt").write_text(
        f"PASS: {len(expected)} source files preserved byte-for-byte.\n"
        "PASS: only the SDK package file list is added.\n"
        "PASS: package identity, noarch architecture, dependencies and hooks checked.\n"
    )
    print((output / "payload-verification.txt").read_text(), end="")


if __name__ == "__main__":
    main()

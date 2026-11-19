#!/usr/bin/env python3
"""Validate SDK-extracted theme and i18n APKs against the committed source payload."""
from __future__ import annotations

import hashlib
import pathlib
import re
import struct
import sys


def verify_lmo(data: bytes) -> int:
    assert len(data) >= 20 and len(data) % 4 == 0, f"Invalid LMO size: {len(data)}"
    (index_offset,) = struct.unpack(">I", data[-4:])
    index_bytes = len(data) - 4 - index_offset
    assert 0 < index_offset < len(data) - 4 and index_offset % 4 == 0, f"Invalid LMO index offset: {index_offset}"
    assert index_bytes > 0 and index_bytes % 16 == 0, f"Invalid LMO index size: {index_bytes}"
    return index_bytes // 16


def main() -> None:
    repo, payload, output, i18n_payload = (pathlib.Path(value) for value in sys.argv[1:5])
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

    i18n_actual = {path.relative_to(i18n_payload).as_posix(): path for path in i18n_payload.rglob("*") if path.is_file() or path.is_symlink()}
    lmo_rel = "usr/lib/lua/luci/i18n/mori.zh-cn.lmo"
    allowed_i18n = {lmo_rel, "lib/apk/packages/luci-i18n-mori-zh-cn.list", "etc/uci-defaults/luci-i18n-mori-zh-cn"}
    assert lmo_rel in i18n_actual and set(i18n_actual) <= allowed_i18n, sorted(i18n_actual)
    for name, path in i18n_actual.items():
        assert not path.is_symlink(), f"Unexpected i18n payload symlink: {name}"
    lmo_entries = verify_lmo(i18n_actual[lmo_rel].read_bytes())
    assert lmo_entries >= 10, f"Too few LMO entries: {lmo_entries}"
    i18n_metadata = (output / "i18n-zh-cn-metadata.yaml").read_text()
    for key, value in (("name", "luci-i18n-mori-zh-cn"), ("version", f"{version}-r{release}"), ("arch", "noarch")):
        assert re.search(rf"^\s*{key}:\s*['\"]?{re.escape(value)}['\"]?\s*$", i18n_metadata, re.M), (key, value)
    assert "luci-theme-mori" in i18n_metadata, "Missing luci-theme-mori dependency in i18n package"

    listing = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  /{name}\n" for name, path in sorted(actual.items()))
    (output / "payload-sha256.txt").write_text(listing)
    i18n_listing = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  /{name}\n" for name, path in sorted(i18n_actual.items()))
    (output / "i18n-zh-cn-payload-sha256.txt").write_text(i18n_listing)
    (output / "payload-verification.txt").write_text(
        f"PASS: {len(expected)} source files preserved byte-for-byte.\n"
        "PASS: only the SDK package file list is added.\n"
        "PASS: package identity, noarch architecture, dependencies and hooks checked.\n"
        f"PASS: zh-cn language pack metadata and compiled LMO verified ({lmo_entries} entries).\n"
    )
    print((output / "payload-verification.txt").read_text(), end="")


if __name__ == "__main__":
    main()

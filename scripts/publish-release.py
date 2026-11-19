#!/usr/bin/env python3
"""Publish already tested assets, leaving an incomplete upload as a draft."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


class ReleaseError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


class GitHub:
    def api(self, method, endpoint, data=None, allow_missing=False):
        command = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
        if data is not None:
            command += ["--input", "-"]
        result = subprocess.run(command, input=json.dumps(data) if data is not None else None,
                                encoding="utf-8", capture_output=True)
        if result.returncode:
            if allow_missing and "(HTTP 404)" in result.stderr:
                return None
            raise ReleaseError(f"GitHub {method} {endpoint} failed (exit {result.returncode}).")
        return json.loads(result.stdout)

    def upload(self, repo, tag, path):
        result = subprocess.run(["gh", "release", "upload", tag, str(path),
                                 "--repo", f"github.com/{repo}"], encoding="utf-8", capture_output=True)
        require(result.returncode == 0, f"Upload failed: {path.name}; release remains a draft.")


def load_artifacts(root, tag, commit):
    require(re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag),
            "Expected a stable version tag such as v0.2.0.")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Expected a full lowercase commit SHA.")
    directory = root / "dist/release"
    metadata = root / "dist/release-metadata"
    require(directory.is_dir() and not directory.is_symlink(), "Missing regular release directory.")
    for name in ("release-manifest.json", "release-notes.md"):
        require((metadata / name).is_file() and not (metadata / name).is_symlink(),
                f"Missing regular metadata file: {name}")
    manifest = json.loads((metadata / "release-manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("tag") == tag and manifest.get("commit") == commit
            and manifest.get("version") == tag[1:], "Manifest does not match the tag and commit.")
    assets = manifest.get("assets", [])
    require(isinstance(assets, list) and len(assets) == 8, "Expected exactly eight release assets.")
    expected = {}
    for asset in assets:
        require(isinstance(asset, dict), "Invalid asset record.")
        name = asset.get("name", "")
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", name)
                and name not in expected, "Unsafe or duplicate asset name.")
        require(isinstance(asset.get("size"), int) and asset["size"] > 0
                and isinstance(asset.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]), "Invalid asset digest or size.")
        expected[name] = asset
    version = tag[1:]
    apks = [name for name in expected
            if re.fullmatch(rf"luci-theme-mori-{re.escape(version)}-r[1-9]\d*\.apk", name)]
    i18n_apks = [name for name in expected
                 if re.fullmatch(rf"luci-i18n-mori-zh-cn-{re.escape(version)}-r[1-9]\d*\.apk", name)]
    names = {"APK-SHA256SUMS", "mori-sdk-signing-public.pem",
             f"luci-theme-mori-{version}.tar.gz", f"luci-theme-mori-{version}.tar.gz.sha256",
             f"luci-theme-mori-{version}-sdk-verification.zip",
             f"luci-theme-mori-{version}-sdk-verification.zip.sha256"}
    require(len(apks) == 1 and len(i18n_apks) == 1
            and apks[0].rsplit("-", 1)[1] == i18n_apks[0].rsplit("-", 1)[1]
            and set(expected) == names | set(apks) | set(i18n_apks),
            "Unexpected release filenames.")
    require({path.name for path in directory.iterdir()} == set(expected), "Release directory differs from manifest.")
    for name, asset in expected.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink(), f"Not a regular release asset: {name}")
        require(path.stat().st_size == asset["size"]
                and hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"],
                f"Release asset changed after testing: {name}")
    notes = (metadata / "release-notes.md").read_text(encoding="utf-8").strip()
    require(bool(notes), "Release notes are empty.")
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    body = f"{notes}\n\n<!-- mori-release:{tag}:{commit}:{fingerprint} -->"
    return directory, expected, body


def verify_tag(client, repo, tag, commit):
    obj = client.api("GET", f"repos/{repo}/git/ref/tags/{tag}")["object"]
    for _ in range(10):
        if obj.get("type") == "commit":
            require(obj.get("sha") == commit, "Remote tag no longer points to the tested commit.")
            return
        require(obj.get("type") == "tag" and re.fullmatch(r"[0-9a-f]{40}", obj.get("sha", "")),
                "Tag does not resolve to a commit.")
        obj = client.api("GET", f"repos/{repo}/git/tags/{obj['sha']}")["object"]
    raise ReleaseError("Too many nested annotated tags.")


def verify_release(release, tag, commit, body):
    # target_commitish is ignored by GitHub when the tag already exists.
    # The peeled remote tag and the commit-bound body identify this release.
    require(release.get("tag_name") == tag
            and release.get("name") == f"Mori {tag}" and release.get("body") == body
            and release.get("prerelease") is False,
            "Existing release is not this exact managed publication; nothing was overwritten.")


def verify_assets(release, expected, complete):
    present = set()
    for asset in release.get("assets", []):
        name = asset.get("name")
        require(name in expected and name not in present, "Release contains unexpected or duplicate assets.")
        wanted = expected[name]
        require(asset.get("state") == "uploaded" and asset.get("size") == wanted["size"]
                and asset.get("digest") == "sha256:" + wanted["sha256"],
                f"Remote asset differs from the tested file: {name}; nothing was overwritten.")
        present.add(name)
    require(not complete or present == set(expected), "Release is missing tested assets.")
    return present


def find_release(client, repo, tag):
    endpoint = f"repos/{repo}/releases"
    release = client.api("GET", f"{endpoint}/tags/{tag}", allow_missing=True)
    if release is not None:
        return release
    # The tag endpoint does not reliably expose drafts. Authenticated release
    # listing includes them, which lets a failed upload resume without creating
    # another draft. Refuse ambiguity instead of selecting a duplicate.
    matches = []
    for page in range(1, 101):
        batch = client.api("GET", f"{endpoint}?per_page=100&page={page}")
        require(isinstance(batch, list), "Invalid release listing response.")
        matches.extend(item for item in batch if item.get("tag_name") == tag)
        require(len(matches) <= 1, "Multiple releases use this tag; review the drafts before retrying.")
        if len(batch) < 100:
            return matches[0] if matches else None
    raise ReleaseError("Release listing exceeded the safe lookup limit.")


def publish(root, repo, tag, commit, client=None):
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo), "Expected OWNER/REPOSITORY.")
    directory, expected, body = load_artifacts(root, tag, commit)
    client = client or GitHub()
    verify_tag(client, repo, tag, commit)
    endpoint = f"repos/{repo}/releases"
    release = find_release(client, repo, tag)
    if release is None:
        release = client.api("POST", endpoint, {
            "tag_name": tag, "target_commitish": commit, "name": f"Mori {tag}",
            "body": body, "draft": True, "prerelease": False,
        })
    verify_release(release, tag, commit, body)
    present = verify_assets(release, expected, complete=not release["draft"])
    if not release["draft"]:
        print(f"Already published and verified: {release['html_url']}")
        return release["html_url"]
    for name in sorted(set(expected) - present):
        client.upload(repo, tag, directory / name)
    release = client.api("GET", f"{endpoint}/{release['id']}")
    verify_release(release, tag, commit, body)
    verify_assets(release, expected, complete=True)
    require(release["draft"] is True, "Release state changed while uploading; refusing to modify it.")
    verify_tag(client, repo, tag, commit)
    release = client.api("PATCH", f"{endpoint}/{release['id']}", {"draft": False, "make_latest": "true"})
    verify_release(release, tag, commit, body)
    verify_assets(release, expected, complete=True)
    require(release["draft"] is False, "GitHub did not publish the draft.")
    print(f"Published and verified: {release['html_url']}")
    return release["html_url"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        publish(Path(__file__).resolve().parents[1], args.repo, args.tag, args.commit)
    except (ReleaseError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Release publication stopped: {error}\n")


if __name__ == "__main__":
    main()

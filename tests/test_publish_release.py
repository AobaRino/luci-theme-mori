"""Release publication gates and failure recovery, with no network writes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("publish_release", Path(__file__).resolve().parents[1] / "scripts/publish-release.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TAG = "v0.2.0"
COMMIT = "a" * 40
REPO = "example/luci-theme-mori"


class FakeGitHub:
    def __init__(self):
        self.release = None
        self.writes = []
        self.fail_upload = None
        self.bad_digest = False
        self.commit = COMMIT
        self.annotated = False
        self.move_tag_on_upload = False
        self.lookups = []
        self.list_pages = None

    def api(self, method, endpoint, data=None, allow_missing=False):
        self.lookups.append((method, endpoint))
        if "/git/ref/" in endpoint:
            return {"object": {"type": "tag" if self.annotated else "commit", "sha": "b" * 40 if self.annotated else self.commit}}
        if "/git/tags/" in endpoint:
            return {"object": {"type": "commit", "sha": self.commit}}
        if method == "GET" and "/releases/tags/" in endpoint:
            return copy.deepcopy(self.release) if self.release and not self.release["draft"] else None
        if method == "GET" and "/releases?" in endpoint:
            page = int(endpoint.split("page=")[-1])
            if self.list_pages is not None:
                return copy.deepcopy(self.list_pages.get(page, []))
            return [copy.deepcopy(self.release)] if self.release else []
        if method == "GET":
            return copy.deepcopy(self.release)
        self.writes.append((method, copy.deepcopy(data)))
        if method == "POST":
            self.release = dict(data, id=123, assets=[], html_url="https://github.com/example/luci-theme-mori/releases/tag/" + TAG)
        elif method == "PATCH":
            self.release.update(data)
        return copy.deepcopy(self.release)

    def upload(self, repo, tag, path):
        if path.name == self.fail_upload:
            raise MODULE.ReleaseError("Simulated upload failure")
        self.writes.append(("UPLOAD", path.name))
        self.release["assets"].append({
            "name": path.name, "size": path.stat().st_size, "state": "uploaded",
            "digest": "sha256:" + ("0" * 64 if self.bad_digest else hashlib.sha256(path.read_bytes()).hexdigest()),
        })
        if self.move_tag_on_upload:
            self.commit = "c" * 40


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mori-release-publish-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "dist/release"
        self.metadata = self.root / "dist/release-metadata"
        self.assets.mkdir(parents=True)
        self.metadata.mkdir(parents=True)
        names = ["luci-theme-mori-0.2.0-r1.apk", "mori-sdk-signing-public.pem", "APK-SHA256SUMS",
                 "luci-theme-mori-0.2.0.tar.gz", "luci-theme-mori-0.2.0.tar.gz.sha256",
                 "luci-theme-mori-0.2.0-sdk-verification.zip", "luci-theme-mori-0.2.0-sdk-verification.zip.sha256"]
        self.manifest = {"tag": TAG, "commit": COMMIT, "version": "0.2.0", "assets": []}
        for name in names:
            data = ("fixture:" + name).encode()
            (self.assets / name).write_bytes(data)
            self.manifest["assets"].append({"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        self.save_manifest()
        (self.metadata / "release-notes.md").write_text("Verified release notes\n", encoding="utf-8")
        self.client = FakeGitHub()

    def save_manifest(self):
        (self.metadata / "release-manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def publish(self):
        return MODULE.publish(self.root, REPO, TAG, COMMIT, self.client)

    def test_creates_draft_verifies_uploads_then_publishes(self):
        self.client.annotated = True
        self.publish()
        self.assertTrue(self.client.writes[0][1]["draft"])
        self.assertEqual([method for method, _ in self.client.writes], ["POST"] + ["UPLOAD"] * 7 + ["PATCH"])
        self.assertFalse(self.client.release["draft"])
        self.assertEqual(self.client.writes[-1][1], {"draft": False, "make_latest": "true"})

    def test_failed_upload_stays_draft_and_exact_retry_resumes(self):
        self.client.fail_upload = "luci-theme-mori-0.2.0-r1.apk"
        with self.assertRaises(MODULE.ReleaseError):
            self.publish()
        self.assertTrue(self.client.release["draft"])
        self.assertEqual(len(self.client.release["assets"]), 1)
        self.client.fail_upload = None
        self.client.lookups.clear()
        self.publish()
        self.assertEqual(len(self.client.release["assets"]), 7)
        self.assertEqual(sum(method == "POST" for method, _ in self.client.writes), 1)
        self.assertIn(("GET", f"repos/{REPO}/releases?per_page=100&page=1"), self.client.lookups)

    def test_draft_lookup_paginates_and_rejects_duplicate_drafts(self):
        self.client.fail_upload = "luci-theme-mori-0.2.0-r1.apk"
        with self.assertRaises(MODULE.ReleaseError):
            self.publish()
        unrelated = [{"tag_name": f"v1.0.{index}"} for index in range(100)]
        self.client.list_pages = {1: unrelated, 2: [self.client.release]}
        self.assertEqual(MODULE.find_release(self.client, REPO, TAG)["id"], 123)
        self.client.list_pages[2].append(copy.deepcopy(self.client.release))
        self.client.writes.clear()
        with self.assertRaisesRegex(MODULE.ReleaseError, "Multiple releases"):
            self.publish()
        self.assertEqual(self.client.writes, [])

    def test_existing_tag_uses_peeled_sha_not_creation_hint(self):
        self.publish()
        self.client.release["target_commitish"] = "main"
        self.client.writes.clear()
        self.publish()
        self.assertEqual(self.client.writes, [])

    def test_published_release_retry_is_read_only(self):
        self.publish()
        self.client.writes.clear()
        self.publish()
        self.assertEqual(self.client.writes, [])

    def test_changed_remote_asset_never_overwritten(self):
        self.publish()
        self.client.release["assets"][0]["digest"] = "sha256:" + "0" * 64
        self.client.writes.clear()
        with self.assertRaisesRegex(MODULE.ReleaseError, "differs"):
            self.publish()
        self.assertEqual(self.client.writes, [])

    def test_rebuilt_artifacts_cannot_replace_partial_draft(self):
        self.client.fail_upload = "luci-theme-mori-0.2.0-r1.apk"
        with self.assertRaises(MODULE.ReleaseError):
            self.publish()
        name = self.manifest["assets"][0]["name"]
        (self.assets / name).write_bytes(b"different signed APK")
        self.manifest["assets"][0].update(size=20, sha256=hashlib.sha256(b"different signed APK").hexdigest())
        self.save_manifest()
        self.client.writes.clear()
        with self.assertRaisesRegex(MODULE.ReleaseError, "exact managed publication"):
            self.publish()
        self.assertEqual(self.client.writes, [])

    def test_changed_local_file_rejected_before_api_writes(self):
        (self.assets / "APK-SHA256SUMS").write_text("tampered")
        with self.assertRaisesRegex(MODULE.ReleaseError, "changed after testing"):
            self.publish()
        self.assertEqual(self.client.writes, [])

    def test_wrong_tag_commit_rejected_before_writes(self):
        self.client.commit = "c" * 40
        with self.assertRaisesRegex(MODULE.ReleaseError, "tested commit"):
            self.publish()
        self.assertEqual(self.client.writes, [])

    def test_tag_moving_during_upload_keeps_draft(self):
        self.client.move_tag_on_upload = True
        with self.assertRaisesRegex(MODULE.ReleaseError, "tested commit"):
            self.publish()
        self.assertTrue(self.client.release["draft"])
        self.assertNotIn("PATCH", [method for method, _ in self.client.writes])

    def test_server_digest_failure_keeps_draft(self):
        self.client.bad_digest = True
        with self.assertRaisesRegex(MODULE.ReleaseError, "differs"):
            self.publish()
        self.assertTrue(self.client.release["draft"])
        self.assertNotIn("PATCH", [method for method, _ in self.client.writes])

    def test_unsafe_or_duplicate_manifest_is_rejected(self):
        for invalid in ("../leak", self.manifest["assets"][1]["name"]):
            self.manifest["assets"][0]["name"] = invalid
            self.save_manifest()
            with self.assertRaisesRegex(MODULE.ReleaseError, "Unsafe or duplicate"):
                self.publish()
        self.assertEqual(self.client.writes, [])


if __name__ == "__main__":
    unittest.main()

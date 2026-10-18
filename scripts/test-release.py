#!/usr/bin/env python3
"""Release integrity checks without uploading assets or using a signing key."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("release", Path(__file__).with_name("verify-release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="librime-release-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        self.version = "1.17.0-pack.10.0.1"
        self.repo = "example/librime"
        self.commit = "a" * 40
        for name in release.ASSETS:
            (self.dist / name).write_text("fixture " + name)
        self.meta = {"packaging_version": self.version, "packaging_commit": self.commit, "upstream_commit": "b" * 40}
        (self.dist / "build-metadata.json").write_text(json.dumps(self.meta))
        self.checksums = {name: release.digest(self.dist / name) for name in release.ASSETS}
        self.manifest = self.root / "Package.swift"
        text = ""
        for target, name in [("RimeStatic", release.ASSETS[0]), ("RimeDynamic", release.ASSETS[1])]:
            url = f"https://github.com/{self.repo}/releases/download/{self.version}/{name}"
            text += f'.binaryTarget(name: "{target}", url: "{url}", checksum: "{self.checksums[name]}")\n'
        self.manifest.write_text(text)
        self.out = self.root / "out"
        self.source = {"UPSTREAM_REPO": "rime/librime", "UPSTREAM_REF": "b" * 40,
                       "UPSTREAM_VERSION": "1.17.0", "UPSTREAM_COMMIT": "b" * 40}
        for name in release.SLICES:
            path = self.out / name
            path.mkdir(parents=True)
            (path / "source.env").write_text("".join(f"{key}={value}\n" for key, value in self.source.items()))

    def test_manifest_matches_final_bytes(self):
        release.check_manifest(self.manifest.read_text(), self.repo, self.version, self.checksums)

    def test_changed_zip_checksum_is_rejected(self):
        self.checksums[release.ASSETS[1]] = "f" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            release.check_manifest(self.manifest.read_text(), self.repo, self.version, self.checksums)

    def test_wrong_repository_or_tag_is_rejected(self):
        for repo, version in [("other/repo", self.version), (self.repo, "1.17.0-pack.10.0.2")]:
            with self.subTest(repo=repo, version=version), self.assertRaises(ValueError):
                release.check_manifest(self.manifest.read_text(), repo, version, self.checksums)

    def test_swapped_static_dynamic_checksums_are_rejected(self):
        a, b = [self.checksums[name] for name in release.ASSETS[:2]]
        text = self.manifest.read_text().replace(a, "PLACEHOLDER").replace(b, a).replace("PLACEHOLDER", b)
        with self.assertRaises(ValueError):
            release.check_manifest(text, self.repo, self.version, self.checksums)

    def test_slices_match(self):
        self.assertEqual(release.check_slices(self.out), self.source)

    def test_different_slice_source_is_rejected(self):
        p = self.out / "ios-arm64/source.env"
        p.write_text(p.read_text().replace("b" * 40, "c" * 40))
        with self.assertRaisesRegex(ValueError, "different upstream"):
            release.check_slices(self.out)

    def test_dirty_source_revision_is_rejected(self):
        p = self.out / "ios-arm64/source.env"
        p.write_text(p.read_text().replace("b" * 40, "b" * 40 + "-dirty"))
        with self.assertRaisesRegex(ValueError, "clean, resolved"):
            release.check_slices(self.out)

    def test_metadata_source_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "metadata"):
            release.check_distribution(self.dist, self.manifest, self.repo, self.version, "c" * 40)

    def test_signed_distribution_requires_a_matching_zip(self):
        with patch.object(release, "check_zip") as verify:
            release.check_distribution(self.dist, self.manifest, self.repo, self.version, self.commit,
                                       out=self.out, signed=True, team_id="ABCDEFGHIJ")
        verify.assert_called_once_with(self.dist / release.ASSETS[1], signed=True, team_id="ABCDEFGHIJ")

    def test_wrong_signer_team_is_rejected(self):
        details = subprocess.CompletedProcess([], 0, "", "Authority=Apple Development: Fixture\nTeamIdentifier=ABCDEFGHIJ\n")
        with patch.object(release.privacy, "verify_bundle"), patch.object(release.subprocess, "run", return_value=details):
            with self.assertRaisesRegex(ValueError, "different Apple team"):
                release.check_signature(Path("fixture"), "KLMNOPQRST")

    def test_developer_id_identity_is_not_accepted_as_apple_development(self):
        details = subprocess.CompletedProcess([], 0, "", "Authority=Developer ID Application: Fixture\nTeamIdentifier=ABCDEFGHIJ\n")
        with patch.object(release.privacy, "verify_bundle"), patch.object(release.subprocess, "run", return_value=details):
            with self.assertRaisesRegex(ValueError, "Apple Development or Apple Distribution"):
                release.check_signature(Path("fixture"), "ABCDEFGHIJ")

    def remote(self, draft=True):
        return {"tag_name": self.version, "draft": draft, "target_commitish": self.commit,
                "assets": [{"name": name} for name in release.ASSETS]}

    def test_public_release_is_never_replaced(self):
        with patch.object(release.subprocess, "check_output", return_value=json.dumps(self.remote(False))):
            with self.assertRaisesRegex(ValueError, "existing public release"):
                release.check_remote(self.dist, self.repo, self.version, self.commit)

    def test_uploaded_bytes_are_compared(self):
        def download(args, **kwargs):
            target = Path(args[args.index("--dir") + 1])
            for name in release.ASSETS:
                (target / name).write_bytes((self.dist / name).read_bytes())
            (target / release.ASSETS[1]).write_bytes(b"corrupt upload")
        with patch.object(release.subprocess, "check_output", return_value=json.dumps(self.remote())), patch.object(release.subprocess, "run", side_effect=download):
            with self.assertRaisesRegex(ValueError, "uploaded release bytes differ"):
                release.check_remote(self.dist, self.repo, self.version, self.commit)

    def test_ci_helpers_refuse_local_execution(self):
        env = dict(os.environ, GITHUB_ACTIONS="false")
        for name in ("sign-ci-sdk.sh", "publish-release.sh"):
            result = subprocess.run([str(release.ROOT / "scripts" / name)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("GitHub-hosted", result.stderr)

    def test_ci_signer_checks_configuration_before_keychain_access(self):
        env = dict(os.environ, GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted",
                   RUNNER_TEMP=str(self.root), GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1",
                   SDK_SIGNING_CERTIFICATE_P12_BASE64="fixture", SDK_SIGNING_CERTIFICATE_PASSWORD="fixture",
                   SDK_SIGNING_IDENTITY="invalid", SDK_SIGNING_TEAM_ID="ABCDEFGHIJ")
        result = subprocess.run([str(release.ROOT / "scripts/sign-ci-sdk.sh"), str(self.dist)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("SHA-1", result.stderr)
        self.assertFalse((self.root / "sdk-signing-1-1").exists())


if __name__ == "__main__":
    unittest.main()

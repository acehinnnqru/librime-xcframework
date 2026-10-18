#!/usr/bin/env python3
"""Regression tests for missing SDK resources and unreviewed API imports."""
import importlib.util
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("privacy_check", Path(__file__).with_name("verify-sdk-privacy.py"))
check = importlib.util.module_from_spec(spec)
# Do not leave __pycache__ in the repository.
import sys
sys.dont_write_bytecode = True
spec.loader.exec_module(check)


class SDKPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="librime-sdk-privacy-")
        self.addCleanup(self.work.cleanup)
        self.bundle = Path(self.work.name) / "librime-dynamic.xcframework"
        self.bundle.mkdir()
        libraries = []
        self.manifests = []
        for identifier, platform, variant in [("macos", "macos", ""), ("ios", "ios", ""), ("sim", "ios", "simulator")]:
            framework = self.bundle / identifier / "RimeDynamic.framework"
            content = framework / "Versions/A" if platform == "macos" else framework
            content.mkdir(parents=True)
            (content / "RimeDynamic").write_bytes(b"fixture")
            manifest = content / "Resources/PrivacyInfo.xcprivacy" if platform == "macos" else content / "PrivacyInfo.xcprivacy"
            manifest.parent.mkdir(exist_ok=True)
            manifest.write_bytes(check.MANIFEST.read_bytes())
            self.manifests.append(manifest)
            entry = {"LibraryIdentifier": identifier, "LibraryPath": "RimeDynamic.framework", "SupportedPlatform": platform}
            if variant:
                entry["SupportedPlatformVariant"] = variant
            libraries.append(entry)
        (self.bundle / "Info.plist").write_bytes(plistlib.dumps({"AvailableLibraries": libraries}))

    def test_flat_ios_and_versioned_macos_manifests(self):
        check.verify_bundle(self.bundle, audit_binary=False)

    def test_missing_sdk_manifest_fails(self):
        self.manifests[1].unlink()
        with self.assertRaises(FileNotFoundError):
            check.verify_bundle(self.bundle, audit_binary=False)

    def test_divergent_manifest_fails(self):
        value = plistlib.loads(self.manifests[0].read_bytes())
        value["NSPrivacyAccessedAPITypes"][0]["NSPrivacyAccessedAPITypeReasons"].append("3B52.1")
        self.manifests[0].write_bytes(plistlib.dumps(value))
        with self.assertRaisesRegex(ValueError, "differs"):
            check.verify_bundle(self.bundle, audit_binary=False)

    def test_unreviewed_disk_and_boot_imports_fail(self):
        _, reasons = check.read_manifest(check.MANIFEST)
        for symbol in ("_statfs", "_statfs$INODE64", "_mach_absolute_time"):
            with self.subTest(symbol=symbol), patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, symbol + "\n")):
                with self.assertRaisesRegex(ValueError, "reviewed reason"):
                    check.inspect_binary(Path("fixture"), reasons)

    def test_database_stat_import_is_declared(self):
        _, reasons = check.read_manifest(check.MANIFEST)
        with patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "_stat$INODE64\n_fstat\n")):
            check.inspect_binary(Path("fixture"), reasons)

    def test_adhoc_signature_is_rejected(self):
        result = subprocess.CompletedProcess([], 0, "", "Signature=adhoc\n")
        with patch.object(check.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "certificate-backed"):
                check.verify_bundle(self.bundle, audit_binary=False, require_signature=True)

    def test_signature_without_secure_timestamp_is_rejected(self):
        result = subprocess.CompletedProcess([], 0, "", "Authority=Apple Distribution: Fixture\n")
        with patch.object(check.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "secure timestamp"):
                check.verify_bundle(self.bundle, audit_binary=False, require_signature=True)

    def test_signature_verification_failure_is_not_ignored(self):
        failure = subprocess.CalledProcessError(1, ["codesign"], stderr="invalid signature")
        with patch.object(check.subprocess, "run", side_effect=failure):
            with self.assertRaises(subprocess.CalledProcessError):
                check.verify_bundle(self.bundle, audit_binary=False, require_signature=True)

    def test_certificate_signature_with_timestamp_passes(self):
        result = subprocess.CompletedProcess([], 0, "", "Authority=Apple Distribution: Fixture\nTimestamp=fixture\n")
        with patch.object(check.subprocess, "run", return_value=result):
            check.verify_bundle(self.bundle, audit_binary=False, require_signature=True)


if __name__ == "__main__":
    unittest.main()

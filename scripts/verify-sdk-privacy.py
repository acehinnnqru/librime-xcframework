#!/usr/bin/env python3
"""Validate dynamic SDK manifests, selected required-reason imports and SDK signing."""
import argparse
import plistlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "privacy/PrivacyInfo.xcprivacy"


def read_manifest(path):
    with path.open("rb") as stream:
        value = plistlib.load(stream)
    if value.get("NSPrivacyTracking") is not False:
        raise ValueError(f"{path}: this distribution must not track users")
    for key in ("NSPrivacyTrackingDomains", "NSPrivacyCollectedDataTypes"):
        if value.get(key) != []:
            raise ValueError(f"{path}: {key} must be an empty array")
    reasons = {}
    for entry in value.get("NSPrivacyAccessedAPITypes", []):
        category = entry["NSPrivacyAccessedAPIType"]
        codes = entry["NSPrivacyAccessedAPITypeReasons"]
        if category in reasons or not codes or len(codes) != len(set(codes)):
            raise ValueError(f"{path}: duplicate category or invalid reason list")
        if any(not re.fullmatch(r"[A-Z0-9]{4}\.[0-9]+", code) for code in codes):
            raise ValueError(f"{path}: malformed reason code")
        reasons[category] = set(codes)
    if "C617.1" not in reasons.get("NSPrivacyAccessedAPICategoryFileTimestamp", set()):
        raise ValueError(f"{path}: database file metadata requires C617.1")
    return value, reasons


def inspect_binary(binary, reasons):
    # This is a narrow regression guard, not a complete privacy/source audit.
    output = subprocess.run(["xcrun", "nm", "-u", str(binary)], check=True,
                            capture_output=True, text=True).stdout
    families = {
        "FileTimestamp": r"_(?:stat|fstat|lstat|fstatat|getattrlist|getattrlistbulk|fgetattrlist|getattrlistat)(?:\$[^\s]+)?",
        "SystemBootTime": r"_mach_absolute_time",
        "DiskSpace": r"_(?:statfs|fstatfs|statvfs|fstatvfs)(?:\$[^\s]+)?",
    }
    for family, pattern in families.items():
        if re.search(r"(?m)(?<!\S)" + pattern + r"$", output):
            if not reasons.get("NSPrivacyAccessedAPICategory" + family):
                raise ValueError(f"{binary}: {family} import needs a reviewed reason in the SDK manifest")


def verify_bundle(bundle, *, audit_binary=True, require_signature=False):
    expected, reasons = read_manifest(MANIFEST)
    with (bundle / "Info.plist").open("rb") as stream:
        libraries = plistlib.load(stream)["AvailableLibraries"]
    platforms = set()
    if len(libraries) != 3:
        raise ValueError("expected macOS, iOS device and iOS simulator slices")
    for entry in libraries:
        identifier = entry["LibraryIdentifier"]
        library = entry["LibraryPath"]
        if Path(identifier).name != identifier or library != "RimeDynamic.framework":
            raise ValueError("unexpected library path in dynamic XCFramework")
        platform = (entry["SupportedPlatform"], entry.get("SupportedPlatformVariant", ""))
        if platform in platforms:
            raise ValueError("duplicate platform slice")
        platforms.add(platform)
        framework = bundle / identifier / library
        if platform == ("macos", ""):
            manifest = framework / "Versions/A/Resources/PrivacyInfo.xcprivacy"
            binary = framework / "Versions/A/RimeDynamic"
        else:
            manifest = framework / "PrivacyInfo.xcprivacy"
            binary = framework / "RimeDynamic"
        actual, _ = read_manifest(manifest)
        if actual != expected:
            raise ValueError(f"{manifest}: differs from the reviewed SDK manifest")
        if not binary.is_file():
            raise ValueError(f"missing dynamic library: {binary}")
        if audit_binary:
            inspect_binary(binary, reasons)
    if platforms != {("macos", ""), ("ios", ""), ("ios", "simulator")}:
        raise ValueError("missing or unsupported platform slice")
    if require_signature:
        subprocess.run(["codesign", "--verify", "--strict", "--verbose=2", str(bundle)], check=True)
        details = subprocess.run(["codesign", "--display", "--verbose=4", str(bundle)],
                                 check=True, capture_output=True, text=True).stderr
        if "Authority=" not in details or "Signature=adhoc" in details:
            raise ValueError("SDK needs a certificate-backed signature, not ad-hoc signing")
        if "Timestamp=" not in details:
            raise ValueError("SDK signature has no secure timestamp")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path)
    parser.add_argument("--require-signature", action="store_true")
    args = parser.parse_args()
    if args.require_signature and args.bundle is None:
        parser.error("--require-signature requires an XCFramework")
    try:
        if args.bundle is None:
            read_manifest(MANIFEST)
        else:
            verify_bundle(args.bundle, require_signature=args.require_signature)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", None) or ""
        parser.exit(1, f"SDK privacy/signature check failed: {error}\n{detail}")
    print("SDK privacy checks passed" + ("; signature verified" if args.require_signature else "; signing not checked"))


if __name__ == "__main__":
    main()

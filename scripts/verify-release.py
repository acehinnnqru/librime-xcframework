#!/usr/bin/env python3
"""Check release source, signed SDK ZIPs and uploaded bytes before publication."""
import argparse
import hashlib
import importlib.util
import json
import posixpath
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ("librime-static.xcframework.zip", "librime-dynamic.xcframework.zip", "librime-stub.zip",
          "LICENSE.txt", "THIRD_PARTY_NOTICES.md", "third-party-notices.zip", "build-metadata.json")
SLICES = ("macos-arm64", "macos-x86_64", "ios-arm64", "ios-simulator-arm64", "ios-simulator-x86_64")
spec = importlib.util.spec_from_file_location("sdk_privacy", ROOT / "scripts/verify-sdk-privacy.py")
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest(manifest, repository, version, checksums):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid GitHub repository")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-pack\.[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("invalid packaging version")
    for target, name in (("RimeStatic", ASSETS[0]), ("RimeDynamic", ASSETS[1])):
        pattern = (r'\.binaryTarget\(\s*name:\s*"' + target
                   + r'",\s*url:\s*"([^"\n]+)",\s*checksum:\s*"([0-9a-f]{64})"\s*\)')
        expected = f"https://github.com/{repository}/releases/download/{version}/{name}"
        if re.findall(pattern, manifest) != [(expected, checksums[name])]:
            raise ValueError(f"{target}: manifest URL/checksum does not match final release ZIP")


def check_slices(out):
    records = []
    keys = ("UPSTREAM_REPO", "UPSTREAM_REF", "UPSTREAM_VERSION", "UPSTREAM_COMMIT")
    for name in SLICES:
        values = dict(line.split("=", 1) for line in (out / name / "source.env").read_text().splitlines())
        record = {key: values[key] for key in keys}
        if not re.fullmatch(r"[0-9a-f]{40}", record["UPSTREAM_COMMIT"]):
            raise ValueError(f"{name}: release source must be a clean, resolved Git commit")
        records.append(record)
    if any(record != records[0] for record in records[1:]):
        raise ValueError("platform slices were built from different upstream sources")
    return records[0]


def check_signature(bundle, team_id):
    privacy.verify_bundle(bundle, require_signature=True)
    details = subprocess.run(["codesign", "--display", "--verbose=4", str(bundle)],
                             check=True, capture_output=True, text=True).stderr
    if not re.fullmatch(r"[A-Z0-9]{10}", team_id):
        raise ValueError("invalid expected Apple team ID")
    if f"TeamIdentifier={team_id}" not in details.splitlines():
        raise ValueError("SDK signature belongs to a different Apple team")
    if not any(line.startswith(("Authority=Apple Development:", "Authority=Apple Distribution:")) for line in details.splitlines()):
        raise ValueError("SDK must use an Apple Development or Apple Distribution identity")


def check_zip(archive, signed=False, team_id=None):
    # ditto preserves framework symlinks. Validate names/links before extraction.
    with zipfile.ZipFile(archive) as stream:
        for item in stream.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("unsafe SDK ZIP member")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                link = stream.read(item).decode("utf-8")
                target = posixpath.normpath(posixpath.join("/candidate", str(name.parent), link))
                if target != "/candidate" and not target.startswith("/candidate/"):
                    raise ValueError("unsafe SDK ZIP symlink")
        links = {item.filename.rstrip("/") for item in stream.infolist()
                 if (item.external_attr >> 16) & 0o170000 == 0o120000}
        for item in stream.infolist():
            if any(str(parent) in links for parent in PurePosixPath(item.filename).parents):
                raise ValueError("SDK ZIP contains members beneath a symlink")
    with tempfile.TemporaryDirectory(prefix="librime-release-verify-") as work:
        subprocess.run(["ditto", "-x", "-k", str(archive), work], check=True)
        bundle = Path(work) / "librime-dynamic.xcframework"
        if signed:
            if not team_id:
                raise ValueError("signed release verification needs the expected Apple team ID")
            check_signature(bundle, team_id)
        else:
            privacy.verify_bundle(bundle)


def check_distribution(dist, manifest, repository, version, source_commit, out=None, signed=False, team_id=None):
    checksums = {name: digest(dist / name) for name in ASSETS}
    check_manifest(manifest.read_text(), repository, version, checksums)
    metadata = json.loads((dist / "build-metadata.json").read_text())
    if metadata["packaging_version"] != version or metadata["packaging_commit"] != source_commit:
        raise ValueError("release metadata does not match the build version/source commit")
    if out:
        source = check_slices(out)
        if metadata["upstream_commit"] != source["UPSTREAM_COMMIT"]:
            raise ValueError("release metadata does not match platform slice sources")
        if not version.startswith(source["UPSTREAM_VERSION"] + "-pack."):
            raise ValueError("release tag does not match the upstream engine version")
    check_zip(dist / ASSETS[1], signed=signed, team_id=team_id)
    return checksums


def check_remote(dist, repository, version, release_commit):
    release = json.loads(subprocess.check_output(["gh", "api", f"repos/{repository}/releases/tags/{version}"], text=True))
    if release["tag_name"] != version or not release["draft"]:
        raise ValueError("refusing to modify or republish an existing public release")
    if release["target_commitish"] != release_commit:
        raise ValueError("draft release points at a different commit")
    if {item["name"] for item in release["assets"]} != set(ASSETS) or len(release["assets"]) != len(ASSETS):
        raise ValueError("draft release asset inventory is incomplete or unexpected")
    with tempfile.TemporaryDirectory(prefix="librime-upload-verify-") as work:
        subprocess.run(["gh", "release", "download", version, "--repo", repository, "--dir", work], check=True)
        for name in ASSETS:
            if digest(Path(work) / name) != digest(dist / name):
                raise ValueError(f"uploaded release bytes differ: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    signature = commands.add_parser("signature")
    signature.add_argument("bundle", type=Path)
    signature.add_argument("--team-id", required=True)
    verify = commands.add_parser("distribution")
    verify.add_argument("--dist", type=Path, default=Path("dist"))
    verify.add_argument("--manifest", type=Path, default=Path("Package.swift"))
    verify.add_argument("--repository", required=True)
    verify.add_argument("--version", required=True)
    verify.add_argument("--source-commit", required=True)
    verify.add_argument("--slices", type=Path)
    verify.add_argument("--signed", action="store_true")
    verify.add_argument("--team-id")
    remote = commands.add_parser("remote")
    remote.add_argument("--dist", type=Path, default=Path("dist"))
    remote.add_argument("--repository", required=True)
    remote.add_argument("--version", required=True)
    remote.add_argument("--release-commit", required=True)
    args = parser.parse_args()
    try:
        if args.command == "signature":
            check_signature(args.bundle, args.team_id)
        elif args.command == "distribution":
            check_distribution(args.dist, args.manifest, args.repository, args.version, args.source_commit,
                               out=args.slices, signed=args.signed, team_id=args.team_id)
        else:
            check_remote(args.dist, args.repository, args.version, args.release_commit)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", None) or ""
        parser.exit(1, f"Release verification failed: {error}\n{detail}")
    print("Release verification passed")


if __name__ == "__main__":
    main()

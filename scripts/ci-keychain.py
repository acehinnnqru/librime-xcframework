#!/usr/bin/env python3
"""Manage the ephemeral CI keychain search list and validate its signing identity."""
import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path


def save_search_list(state):
    output = subprocess.check_output(["security", "list-keychains", "-d", "user"], text=True)
    state.write_text(json.dumps(shlex.split(output)))


def activate_keychain(state, keychain):
    original = json.loads(state.read_text())
    entries = list(dict.fromkeys([str(keychain), *original]))
    subprocess.run(["security", "list-keychains", "-d", "user", "-s", *entries], check=True)


def restore_search_list(state):
    original = json.loads(state.read_text())
    subprocess.run(["security", "list-keychains", "-d", "user", "-s", *original], check=True)


def verify_identity(keychain, identity):
    if not re.fullmatch(r"[A-Fa-f0-9]{40}", identity):
        raise ValueError("SDK_SIGNING_IDENTITY must be a 40-character SHA-1 fingerprint")
    output = subprocess.check_output(
        ["security", "find-identity", "-v", "-p", "codesigning", str(keychain)], text=True)
    fingerprints = re.findall(r'^\s*\d+\)\s+([A-Fa-f0-9]{40})\s', output, re.MULTILINE)
    if identity.upper() not in [value.upper() for value in fingerprints]:
        found = ", ".join(fingerprints) or "none"
        raise ValueError(
            "The imported P12 has no valid code-signing identity matching SDK_SIGNING_IDENTITY. "
            "Export the certificate with its private key and set SDK_SIGNING_IDENTITY to that "
            "same certificate's SHA-1 fingerprint. Check certificate validity/trust if no valid "
            f"identities are listed. Valid imported fingerprints: {found}")
    print("Configured signing identity is available in the temporary keychain")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("save", "activate", "restore", "verify-identity"))
    parser.add_argument("state", type=Path, nargs="?")
    parser.add_argument("--keychain", type=Path)
    parser.add_argument("--identity")
    args = parser.parse_args()
    if args.command != "verify-identity" and args.state is None:
        parser.error("search-list state path is required")
    if args.command in ("activate", "verify-identity") and args.keychain is None:
        parser.error("--keychain is required")
    if args.command == "verify-identity" and not args.identity:
        parser.error("--identity is required")
    try:
        if args.command == "save":
            save_search_list(args.state)
        elif args.command == "activate":
            activate_keychain(args.state, args.keychain)
        elif args.command == "restore":
            restore_search_list(args.state)
        else:
            verify_identity(args.keychain, args.identity)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"CI keychain setup failed: {error}\n")


if __name__ == "__main__":
    main()

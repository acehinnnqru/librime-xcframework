#!/usr/bin/env bash
# Sign an already-built dynamic SDK using an existing local keychain identity.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 || -z "$2" || "$2" == "-" ]]; then
  echo "usage: $0 <distribution-directory> <Apple signing identity> [keychain]" >&2
  exit 2
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist_dir="$(cd "$1" && pwd)"
identity="$2"
bundle="${dist_dir}/librime-dynamic.xcframework"
python3 "${script_dir}/verify-sdk-privacy.py" "${bundle}"
# Never silently replace an existing signature or change keychain settings.
if codesign --display "${bundle}" >/dev/null 2>&1; then
  echo "SDK is already signed; use a fresh build instead of overwriting its signature." >&2
  exit 1
fi
if [[ $# -eq 3 ]]; then
  codesign --timestamp --sign "${identity}" --keychain "$3" "${bundle}"
else
  codesign --timestamp --sign "${identity}" "${bundle}"
fi
python3 "${script_dir}/verify-sdk-privacy.py" "${bundle}" --require-signature
# Signing changes the bytes and therefore the SwiftPM checksum. The input
# directory must contain the unpacked SDK, not just CI's release ZIPs.
# Remove the old ZIP: ditto must not update an archive with stale entries.
rm -f "${dist_dir}/librime-dynamic.xcframework.zip"
(cd "${dist_dir}" && ditto -c -k --sequesterRsrc --keepParent \
  librime-dynamic.xcframework librime-dynamic.xcframework.zip)
echo "Signed dynamic SDK ZIP checksum (regenerate the SwiftPM manifest before release):"
swift package compute-checksum "${dist_dir}/librime-dynamic.xcframework.zip"
echo "Static SDK signing/resources are outside this dynamic SDK flow. Nothing was published."

#!/usr/bin/env bash
# Use a temporary keychain only on an ephemeral GitHub-hosted macOS runner.
set -euo pipefail
set +x
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || -z "${RUNNER_TEMP:-}" ]]; then
  echo "CI signing requires a GitHub-hosted runner; use sign-local-sdk.sh locally." >&2
  exit 2
fi
for name in GITHUB_RUN_ID GITHUB_RUN_ATTEMPT; do
  if [[ ! "${!name:-}" =~ ^[0-9]+$ ]]; then
    echo "Missing or invalid runner identity: ${name}" >&2
    exit 2
  fi
done
work_dir="${RUNNER_TEMP}/sdk-signing-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
keychain="${work_dir}/sdk.keychain-db"
cleanup() {
  if [[ -d "${work_dir}" ]]; then
    security delete-keychain "${keychain}" >/dev/null 2>&1 || true
    rm -rf "${work_dir}"
  fi
}
if [[ "${1:-}" == --cleanup && $# -eq 1 ]]; then
  cleanup
  exit 0
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 <distribution-directory> | --cleanup" >&2
  exit 2
fi
for name in SDK_SIGNING_CERTIFICATE_P12_BASE64 SDK_SIGNING_CERTIFICATE_PASSWORD SDK_SIGNING_IDENTITY SDK_SIGNING_TEAM_ID; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing CI signing configuration: ${name}" >&2
    exit 2
  fi
done
if [[ ! "${SDK_SIGNING_IDENTITY}" =~ ^[0-9A-Fa-f]{40}$ || ! "${SDK_SIGNING_TEAM_ID}" =~ ^[A-Z0-9]{10}$ ]]; then
  echo "SDK signing identity must be a SHA-1 fingerprint and team ID must contain 10 uppercase letters/digits." >&2
  exit 2
fi
umask 077
mkdir "${work_dir}"
trap cleanup EXIT
password="$(openssl rand -base64 32)"
echo "::add-mask::${password}"
python3 - "${work_dir}/certificate.p12" <<'CERTIFICATE'
import base64, os, pathlib, sys
encoded = "".join(os.environ["SDK_SIGNING_CERTIFICATE_P12_BASE64"].split())
pathlib.Path(sys.argv[1]).write_bytes(base64.b64decode(encoded, validate=True))
CERTIFICATE
security create-keychain -p "${password}" "${keychain}"
security set-keychain-settings -lut 3600 "${keychain}"
security unlock-keychain -p "${password}" "${keychain}"
security import "${work_dir}/certificate.p12" -P "${SDK_SIGNING_CERTIFICATE_PASSWORD}" \
  -t cert -f pkcs12 -k "${keychain}" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "${password}" "${keychain}" >/dev/null
rm -f "${work_dir}/certificate.p12"
unset SDK_SIGNING_CERTIFICATE_P12_BASE64 SDK_SIGNING_CERTIFICATE_PASSWORD
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${script_dir}/sign-local-sdk.sh" "$1" "${SDK_SIGNING_IDENTITY}" "${keychain}"
python3 "${script_dir}/verify-release.py" signature "$1/librime-dynamic.xcframework" --team-id "${SDK_SIGNING_TEAM_ID}"

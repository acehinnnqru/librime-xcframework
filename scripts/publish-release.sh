#!/usr/bin/env bash
# Release automation may create unsigned generated-file commits by user authorization.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo "Publication is restricted to the GitHub-hosted release workflow." >&2
  exit 2
fi
for name in GITHUB_REF_TYPE GITHUB_REF_NAME RELEASE_BRANCH GITHUB_SHA GITHUB_REPOSITORY PACKAGING_VERSION UPSTREAM_REPO UPSTREAM_REF SDK_SIGNING_TEAM_ID GH_TOKEN; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing release configuration: ${name}" >&2
    exit 2
  fi
done
if [[ "${GITHUB_REF_TYPE}" != branch || "${GITHUB_REF_NAME}" != "${RELEASE_BRANCH}" ]]; then
  echo "Release must run from the configured default branch." >&2
  exit 1
fi
python3 scripts/verify-release.py distribution \
  --repository "${GITHUB_REPOSITORY}" --version "${PACKAGING_VERSION}" \
  --source-commit "${GITHUB_SHA}" --slices out --signed --team-id "${SDK_SIGNING_TEAM_ID}"
if [[ "$(git rev-parse HEAD)" != "${GITHUB_SHA}" ]]; then
  echo "Checkout moved since this workflow started." >&2
  exit 1
fi
git fetch --no-tags origin "${RELEASE_BRANCH}"
if [[ "$(git rev-parse FETCH_HEAD)" != "${GITHUB_SHA}" ]]; then
  echo "Release branch advanced during the build; rerun from its new head." >&2
  exit 1
fi
tags="$(git ls-remote --tags origin "refs/tags/${PACKAGING_VERSION}" "refs/tags/${PACKAGING_VERSION}^{}")"
if [[ -n "${tags}" ]]; then
  echo "Release tag already exists; choose a new version. Existing signed assets are never replaced." >&2
  exit 1
fi
releases="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/releases" --jq '.[].tag_name')"
if printf '%s\n' "${releases}" | grep -Fxq "${PACKAGING_VERSION}"; then
  echo "A release already exists for this version; refusing to overwrite it." >&2
  exit 1
fi
# Only generated release source is staged. This runner does not receive a GPG
# private key; the user explicitly authorized unsigned automation commits.
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
if ! git diff --cached --quiet; then
  echo "Unexpected staged changes before release generation." >&2
  exit 1
fi
git add Package.swift Sources/RimeHeaders Sources/RimeSystem Sources/RimeOpenCCData
if ! git diff --cached --quiet; then
  git commit -m "release: ${PACKAGING_VERSION}"
fi
release_commit="$(git rev-parse HEAD)"
git tag "${PACKAGING_VERSION}"
# A non-fast-forward branch rejection must also prevent the tag from appearing.
git push --atomic origin "HEAD:refs/heads/${RELEASE_BRANCH}" "refs/tags/${PACKAGING_VERSION}"
remote_tag="$(git ls-remote --tags origin "refs/tags/${PACKAGING_VERSION}" | awk '{print $1}')"
if [[ "${remote_tag}" != "${release_commit}" ]]; then
  echo "Remote release tag does not match the generated manifest commit." >&2
  exit 1
fi
assets=(
  dist/librime-static.xcframework.zip
  dist/librime-dynamic.xcframework.zip
  dist/librime-stub.zip
  dist/LICENSE.txt
  dist/THIRD_PARTY_NOTICES.md
  dist/third-party-notices.zip
  dist/build-metadata.json
)
notes="Static and dynamic macOS/iOS XCFrameworks for ${UPSTREAM_REPO}@${UPSTREAM_REF}. The dynamic SDK includes privacy manifests and an Apple SDK signature."
gh release create "${PACKAGING_VERSION}" "${assets[@]}" --draft --verify-tag \
  --target "${release_commit}" --title "${PACKAGING_VERSION}" --notes "${notes}"
# Check the uploaded bytes before the draft becomes publicly consumable.
python3 scripts/verify-release.py remote --repository "${GITHUB_REPOSITORY}" \
  --version "${PACKAGING_VERSION}" --release-commit "${release_commit}"
gh release edit "${PACKAGING_VERSION}" --draft=false --latest

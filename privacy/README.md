# Dynamic SDK privacy, signing and releases

This flow targets `RimeDynamic`, which includes LevelDB and is the binary used
by Arkey. It does not certify the raw static-library XCFramework for App Store
submission. A static SDK needs separate resource delivery work before that claim.

## Manifest scope

The SDK does not implement tracking or data collection. Data stays in files
chosen by the host. Host applications remain responsible for their own telemetry,
callbacks, user-supplied Lua scripts, file permissions, and privacy disclosures.
Keep database and log files in the app or app-group container for this manifest.

`C617.1` covers file timestamp/size metadata in those containers. LevelDB's POSIX
`GetFileSize` uses `stat`; glog's log cleanup and Boost.Interprocess file helpers
also inspect file metadata. Source evidence:

- https://github.com/google/leveldb/blob/1.23/util/env_posix.cc
- https://github.com/google/glog/blob/v0.7.1/src/logging.cc
- https://github.com/boostorg/interprocess/blob/boost-1.88.0/include/boost/interprocess/detail/os_file_functions.hpp
- https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype

These are source examples, not a verified inventory of the exact resolved vcpkg
baseline. Final binaries still need review. The package check inspects selected
undefined POSIX imports and stops on an undeclared disk-space or boot-time API.
It is a regression guard, not a complete source audit: Objective-C selectors,
transitive system-library implementations, dynamic lookup and arbitrary Lua code
are outside its coverage. Do not add speculative reason codes to silence it.
If interval timing actually imports `mach_absolute_time`, review that use before
adding `35F9.1`; LevelDB's `gettimeofday` alone does not require that declaration.
Changes to dependencies and use of external user-selected files need a new review.

The manifest is copied into each iOS framework root and macOS
`Versions/A/Resources` before the XCFramework is assembled. An app-level manifest
does not replace these SDK resources.

## Build-only validation

The flake follows the shared `devshells` convention used by `rt`. It supplies
CMake, Ninja, Python and dependency build helpers without replacing Xcode's
compiler, SDK, `libtool`, or signing utilities. On macOS it also provides vcpkg: `flake.lock` pins the scripts repository,
whose tool metadata supplies the official universal macOS executable's release
and SHA-512 hash. `VCPKG_ROOT` is set automatically to a read-only Nix bundle;
no separate checkout or bootstrap is needed. Dependency versions still come from
`vcpkg.json`, independently of the tool version.

The bundle's read-only mode puts per-build intermediate packages alongside the
manifest installation tree, while downloads use `.build/vcpkg-downloads`.
Versioned port sources and the binary cache use `.build/vcpkg-registries` and
`.build/vcpkg-binary-cache`.
No compiler or dependency output is written into the Nix store. vcpkg telemetry
is disabled in this shell, and its helper tools use the shell's installed binaries.

The flake also provides upstream librime 1.17.0 without submodules and sets
`UPSTREAM_SOURCE_DIR`. Its commit is pinned in `flake.lock`; snapshot metadata
travels with the source and is recorded in build metadata. Builds copy it to a
writable staging directory before applying patches. An explicitly requested
`UPSTREAM_REF` must match the snapshot's tag or commit. Override
`UPSTREAM_SOURCE_DIR` only when intentionally building a separate checkout. Initialize this
repository's plugin submodules before compiling. `flake.lock` should be generated
and reviewed when the environment is first resolved; no dependencies are installed
by entering a hand-written fallback environment.

After direnv has been explicitly authorized for this repository:

```sh
direnv exec . python3 scripts/test-sdk-privacy.py
direnv exec . python3 scripts/test-source-snapshot.py
direnv exec . python3 scripts/verify-sdk-privacy.py
direnv exec . scripts/build-all.sh
```

`build-all.sh` builds all five slices and packages them locally; it has no commit,
tag, push or release step. Run upstream tests separately for the host architecture:

```sh
direnv exec . env BUILD_TESTS=1 scripts/build-one-arch.sh macos-arm64
```

Use `macos-x86_64` on Intel. GitHub `build.yml` defaults to `publish: false` and
`sign_sdk: false`, which builds without signing credentials or remote mutations.
Set `sign_sdk: true` to exercise hosted signing without creating a commit, tag or
release. `publish: true` always signs and performs the release sequence below.
No modified workflow can be tested remotely until the changes exist remotely.

## Local signing

Use an existing Apple Development or Apple Distribution identity in the local
keychain. No private key is exported, no certificate is created and no keychain
settings are changed by these scripts. This step must be explicitly authorized
with the selected identity when operated by an agent.

For CI artifacts, first extract `librime-dynamic.xcframework.zip` into the same
distribution directory so the unpacked XCFramework is present. For a local build
it is already in `dist/`. Then run:

```sh
direnv exec . scripts/sign-local-sdk.sh dist 'Apple Distribution: Your Name (TEAMID)'
```

The script checks resources/imports, rejects an already-signed input, signs the
outer XCFramework with a secure timestamp, verifies the certificate-backed
signature, recreates the dynamic ZIP and prints its new SwiftPM checksum. It
does not sign the static SDK, alter `Package.swift`, commit, upload or publish.
Do not modify the SDK after signing. A failure after signing may leave a signed
candidate or an older ZIP; discard that candidate and start from a fresh build.

For a manually signed build, regenerate `Package.swift` with the final signed
ZIP's checksum and the fork's asset URL before release. The hosted release flow
does this automatically after signing.

## GitHub Actions releases

Configure repository Actions Secrets (not committed files):

| Secret | Value |
| --- | --- |
| `SDK_SIGNING_CERTIFICATE_P12_BASE64` | Base64 of a password-protected `.p12` export containing the selected Apple Development or Apple Distribution certificate and its private key. |
| `SDK_SIGNING_CERTIFICATE_PASSWORD` | Password used for that `.p12` export. |

Configure repository Actions Variables:

| Variable | Value |
| --- | --- |
| `SDK_SIGNING_IDENTITY` | The selected certificate's 40-character SHA-1 fingerprint. |
| `SDK_SIGNING_TEAM_ID` | The expected 10-character Apple team ID; it must match the consuming app's team for this project's release setup. |
| `AUTO_PUBLISH_RELEASES` | Optional. Set to `true` only after a signed smoke run succeeds to enable scheduled upstream publication. Otherwise scheduled runs are build-only. |

Create the `.p12` export yourself in Keychain Access, choosing only the intended
certificate/private-key pair and a strong password. Never commit the export.
To encode an already-exported file on macOS:

```sh
base64 -i /absolute/path/to/certificate.p12 | tr -d '\n' | pbcopy
```

Paste the clipboard into the certificate Secret, not into a workflow file or
chat. The certificate fingerprint is shown by `security find-identity -v -p
codesigning`; the team is the certificate's Organizational Unit. A provisioning
profile is not needed to sign an XCFramework. No script in this repository exports
keys or uploads Secrets.

First dispatch the **build** workflow from the default branch with:

- `upstream_repo: rime/librime`
- `upstream_ref: 1.17.0`
- `sign_sdk: true`
- `publish: false`

This checks hosted signing and the final ZIP, then uploads an Actions artifact
containing `dist/` plus generated SwiftPM source. It does not commit, push or
create a release. After inspection, dispatch with `publish: true`. An empty
`packaging_version` infers the next packaging patch from existing tags; an explicit
version must match the engine version and must be unused.

The publication sequence is:

1. Resolve one upstream commit and use it for all five platform slices and tests.
2. Package the privacy resources. Import the configured identity into a dedicated
   temporary keychain on the GitHub-hosted runner and sign only the dynamic SDK.
3. Verify the certificate-backed signature, secure timestamp, expected team,
   privacy manifests and extracted final ZIP. Delete the temporary `.p12` and
   keychain on exit, with an additional unconditional workflow cleanup step.
4. Compute checksums after signing and generate the final `Package.swift` using
   this fork's release URLs. Verify source metadata agrees across all slices.
5. Create the explicitly user-authorized unsigned bot commit containing only
   generated package/header/API-note/OpenCC files. Push the branch and new tag
   atomically. This exception applies to release automation; local agent commits
   still follow the standing approval and GPG rules.
6. Create a draft with the exact assets, download and compare every uploaded
   file, and only then publish and mark latest.

The workflow rejects publication from a non-default branch, a branch that moved
during the build, an existing version, or a failed signature/checksum check. It
never force-pushes, moves a tag, or replaces published assets. If a failure occurs
after the tag is pushed, preserve the failed attempt for diagnosis and rerun with
a new version; secure timestamps mean a freshly signed ZIP has different bytes.
Draft failures do not count as published releases in the scheduled upstream check.
Branch protections that prohibit bot pushes or unsigned commits will fail the
publication step; changing those protections requires an explicit owner decision.

After the release is public, pin both Arkey dependency declarations to that
release in `acehinnnqru/librime-xcframework`, resolve packages and inspect the
actual Arkey archive before resubmitting it to Apple. The legacy raw static SDK
still needs separate privacy-resource integration; this release flow validates
the dynamic SDK used by Arkey.

Apple references:

- https://developer.apple.com/support/third-party-SDK-requirements/
- https://developer.apple.com/documentation/xcode/creating-a-multi-platform-binary-framework-bundle

Passing local checks does not guarantee App Store acceptance. Validate the actual
Arkey archive and Apple's server-side processing before considering this resolved.

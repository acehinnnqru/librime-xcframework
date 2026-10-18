{lib, stdenvNoCC, fetchurl, vcpkgSource}:
let
  # Use the release and SHA-512 recorded by the locked scripts repository.
  # The dependency baseline remains exclusively in vcpkg.json.
  metadata = builtins.listToAttrs (builtins.filter (entry: entry != null)
    (map (line: let matched = builtins.match "([A-Z0-9_]+)=(.*)" line;
      in if matched == null then null else {
        name = builtins.elemAt matched 0;
        value = builtins.elemAt matched 1;
      }) (lib.splitString "\n" (builtins.readFile "${vcpkgSource}/scripts/vcpkg-tool-metadata.txt"))));
  tool = fetchurl {
    url = "https://github.com/microsoft/vcpkg-tool/releases/download/${metadata.VCPKG_TOOL_RELEASE_TAG}/vcpkg-macos";
    sha512 = metadata.VCPKG_MACOS_SHA;
  };
in stdenvNoCC.mkDerivation {
  pname = "vcpkg-bundle";
  version = metadata.VCPKG_TOOL_RELEASE_TAG;
  dontUnpack = true;
  dontFixup = true;
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/vcpkg" "$out/bin"
    cp -R ${vcpkgSource}/scripts ${vcpkgSource}/triplets "$out/share/vcpkg/"
    cp ${vcpkgSource}/LICENSE.txt "$out/share/vcpkg/LICENSE.txt"
    touch "$out/share/vcpkg/.vcpkg-root"
    cp ${tool} "$out/share/vcpkg/vcpkg"
    chmod +x "$out/share/vcpkg/vcpkg"
    # Read-only bundle mode relocates buildtrees/packages/downloads outside
    # the Nix store and resolves versioned ports through the Git registry.
    cat > "$out/share/vcpkg/vcpkg-bundle.json" <<'JSON'
    ${builtins.toJSON {
      readonly = true;
      usegitregistry = true;
      embeddedsha = vcpkgSource.rev;
    }}
    JSON
    ln -s "$out/share/vcpkg/vcpkg" "$out/bin/vcpkg"
    runHook postInstall
  '';
  meta = {
    description = "Read-only vcpkg tool and CMake integration for Xcode builds";
    homepage = "https://github.com/microsoft/vcpkg";
    license = lib.licenses.mit;
    platforms = lib.platforms.darwin;
  };
}

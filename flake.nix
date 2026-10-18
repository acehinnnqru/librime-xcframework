{
  description = "librime XCFramework build and packaging tools";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    librime = {
      url = "github:rime/librime/1.17.0";
      flake = false;
    };
    vcpkg = {
      url = "github:microsoft/vcpkg";
      flake = false;
    };
    devshells = {
      url = "github:acehinnnqru/devshells";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {nixpkgs, flake-utils, devshells, vcpkg, librime, ...}:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};
      librimeSource = pkgs.runCommand "librime-source-${librime.shortRev}" {} ''
        mkdir -p "$out"
        cp -R ${librime}/. "$out/"
        chmod u+w "$out"
        cat > "$out/.librime-source.json" <<'JSON'
        ${builtins.toJSON {repo = "rime/librime"; ref = "1.17.0"; commit = librime.rev;}}
        JSON
      '';
      isDarwin = pkgs.stdenv.hostPlatform.isDarwin;
      vcpkgPackage = pkgs.callPackage ./nix/vcpkg.nix {vcpkgSource = vcpkg;};
    in {
      packages = pkgs.lib.optionalAttrs isDarwin {vcpkg = vcpkgPackage;};
      devShells.default = pkgs.mkShellNoCC {
        inputsFrom = [devshells.devShells.${system}.default];
        packages = with pkgs; [
          cmake ninja pkg-config python3 git curl zip unzip autoconf automake
          actionlint shellcheck
        ] ++ pkgs.lib.optional isDarwin vcpkgPackage;
        env = {
          UPSTREAM_SOURCE_DIR = "${librimeSource}";
        } // pkgs.lib.optionalAttrs isDarwin {
          VCPKG_ROOT = "${vcpkgPackage}/share/vcpkg";
          VCPKG_DISABLE_METRICS = "1";
          VCPKG_FORCE_SYSTEM_BINARIES = "1";
        };
        # Xcode provides Apple's compiler, SDKs, libtool, signing and packaging.
        # Do not replace them with a Nix compiler or a GNU libtool.
        shellHook = pkgs.lib.optionalString isDarwin ''
          export CC=/usr/bin/clang
          export CXX=/usr/bin/clang++
          export VCPKG_DOWNLOADS="$PWD/.build/vcpkg-downloads"
          export X_VCPKG_REGISTRIES_CACHE="$PWD/.build/vcpkg-registries"
          export VCPKG_DEFAULT_BINARY_CACHE="$PWD/.build/vcpkg-binary-cache"
          mkdir -p "$VCPKG_DOWNLOADS" "$X_VCPKG_REGISTRIES_CACHE" "$VCPKG_DEFAULT_BINARY_CACHE"
        '';
      };
    });
}

{
  lib,
  pkgs,
  repoSubset,
  codegenUnits ? null,
  optLevel ? null,
  workspaceCrates ? [],
}: let
  rustcOpts = lib.optionals (optLevel != null) ["-C opt-level=${toString optLevel}"];

  tuning =
    lib.optionalAttrs (codegenUnits != null) {inherit codegenUnits;}
    // lib.optionalAttrs (rustcOpts != []) {extraRustcOpts = rustcOpts;};

  extraPathsFor = {
    jcode-app-core = ["README.md" "docs"];
    jcode-setup-hints = ["assets/app-icons"];
  };

  extraEnvFor = {
    jcode-build-meta = {
      JCODE_BUILD_GIT_HASH = "nix";
      JCODE_BUILD_GIT_DATE = "unknown";
      JCODE_BUILD_GIT_DIRTY = "0";
      JCODE_BUILD_GIT_TAG = "";
      JCODE_BUILD_CHANGELOG_RAW = "";
    };
  };

  memberDir = crate:
    if crate == "jcode"
    then "."
    else "crates/${crate}";

  ownPaths = crate:
    if crate == "jcode"
    then ["src" "tests"]
    else ["crates/${crate}"];

  workspaceCrateOverride = crate: _attrs:
    {
      src = repoSubset {
        name = "jcode-src-${crate}";
        paths =
          ["Cargo.toml" "Cargo.lock"]
          ++ ownPaths crate
          ++ extraPathsFor.${crate} or [];
      };
      workspace_member = memberDir crate;
    }
    // tuning
    // extraEnvFor.${crate} or {};

  workspaceOverrides =
    lib.genAttrs workspaceCrates workspaceCrateOverride;
in
  workspaceOverrides
  // {
    aws-lc-sys = _attrs: {
      nativeBuildInputs = [pkgs.cmake pkgs.perl];
      env.AWS_LC_SYS_CMAKE_BUILDER = 1;
      dontUseCmakeConfigure = true;
    };

    openssl-sys = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config pkgs.perl];
      buildInputs = [pkgs.openssl];
    };

    libsqlite3-sys = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config];
      buildInputs = [pkgs.sqlite];
    };

    onig_sys = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config];
    };

    tikv-jemalloc-sys = _attrs: {
      nativeBuildInputs = [pkgs.perl];
    };

    fontdb = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config];
      buildInputs = [pkgs.fontconfig];
    };

    jcode-tui-mermaid = _attrs:
      workspaceCrateOverride "jcode-tui-mermaid" _attrs
      // {
        nativeBuildInputs = [pkgs.pkg-config];
        buildInputs = [pkgs.fontconfig];
      };

    jcode-notify-email = _attrs:
      workspaceCrateOverride "jcode-notify-email" _attrs
      // {
        nativeBuildInputs = [pkgs.pkg-config];
        buildInputs = [pkgs.openssl];
      };
  }

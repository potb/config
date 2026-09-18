let
  pkgs = import <nixpkgs> {};
  inherit (pkgs) lib;

  settings = builtins.fromJSON (builtins.readFile (builtins.getEnv "jcodeSettingsPath"));
  inherit (settings) optLevel codegenUnits rootFeatures name;

  rustcOpts = ["-C opt-level=${toString optLevel}"];

  root = ./.;
  rootString = toString root;

  repoSubset = {
    name,
    paths,
  }: let
    keep = path: type: let
      relative = lib.removePrefix (rootString + "/") (toString path);
      isUnder = kept: lib.hasPrefix (kept + "/") (relative + "/");
      isAncestorOf = kept: lib.hasPrefix (relative + "/") (kept + "/");
      wanted = lib.any (kept: isUnder kept || isAncestorOf kept) paths;
      ignored = type == "directory" && (baseNameOf path == "target" || baseNameOf path == ".git");
    in
      wanted && !ignored;
  in
    builtins.path {
      inherit name;
      path = root;
      filter = keep;
    };

  workspaceCrates =
    builtins.attrNames
    (import ./Cargo.nix {
      inherit pkgs;
      buildRustCrateForPkgs = _: _: null;
    })
    .workspaceMembers;

  extraPathsFor = {
    jcode-app-core = ["README.md" "docs"];
    jcode-setup-hints = ["assets/app-icons"];
  };

  extraAttrsFor = {
    jcode = {
      crateBin = [
        {
          name = "jcode";
          path = "src/main.rs";
          requiredFeatures = [];
        }
      ];
      extraRustcOpts = rustcOpts ++ ["-C strip=symbols"];
    };
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
      inherit codegenUnits;
      extraRustcOpts = rustcOpts;
    }
    // extraEnvFor.${crate} or {}
    // extraAttrsFor.${crate} or {};

  crateOverrides =
    lib.genAttrs workspaceCrates workspaceCrateOverride
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

      jcode-tui-mermaid = attrs:
        workspaceCrateOverride "jcode-tui-mermaid" attrs
        // {
          nativeBuildInputs = [pkgs.pkg-config];
          buildInputs = [pkgs.fontconfig];
        };

      jcode-notify-email = attrs:
        workspaceCrateOverride "jcode-notify-email" attrs
        // {
          nativeBuildInputs = [pkgs.pkg-config];
          buildInputs = [pkgs.openssl];
        };
    };

  cargoNix = import ./Cargo.nix {
    inherit pkgs rootFeatures;
    release = true;
    buildRustCrateForPkgs = p:
      p.buildRustCrate.override {
        defaultCrateOverrides = pkgs.defaultCrateOverrides // crateOverrides;
      };
  };
in
  cargoNix.workspaceMembers."jcode".build.overrideAttrs {inherit name;}

let
  pkgs = import <nixpkgs> {};
  inherit (pkgs) lib;

  settings = builtins.fromJSON (builtins.readFile (builtins.getEnv "jcodeSettingsPath"));
  inherit (settings) optLevel codegenUnits name target roots;

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

  memberDirs = builtins.fromJSON (builtins.readFile ./members.json);

  checkoutOf = crate: builtins.head (lib.splitString "/" memberDirs.${crate});

  ownPaths = {
    jcode = ["jcode/src" "jcode/tests"];
    jcode-desktop = ["jcode-desktop/src" "jcode-desktop/build.rs"];
  };

  extraPathsFor = {
    jcode-app-core = ["jcode/README.md" "jcode/docs"];
    jcode-setup-hints = ["jcode/assets/app-icons"];
    jcode-desktop-api = ["jcode-desktop/Cargo.toml"];
    jcode-desktop-harness = ["jcode-desktop/assets" "jcode-desktop/applets"];
    jcode-desktop-model = ["jcode-desktop/assets" "jcode-desktop/applets"];
    jcode-desktop-ui = ["jcode-desktop/assets" "jcode-desktop/applets" "jcode-desktop/CHANGELOG.md"];
    jcode-desktop-ui-core = ["jcode-desktop/assets" "jcode-desktop/applets"];
    jcode-desktop-voice = ["jcode-desktop/assets"];
  };

  extraEnvFor = {
    jcode-build-meta = {
      JCODE_BUILD_GIT_HASH = "nix";
      JCODE_BUILD_GIT_DATE = "unknown";
      JCODE_BUILD_GIT_DIRTY = "0";
      JCODE_BUILD_GIT_TAG = "";
      JCODE_BUILD_CHANGELOG_RAW = "";
    };
    jcode-desktop-ui = {
      JCODE_DESKTOP_VERSION = settings.desktopVersion;
      SOURCE_DATE_EPOCH = "1";
    };
  };

  binary = crate: {
    crateBin = [
      {
        name = crate;
        path = "src/main.rs";
        requiredFeatures = [];
      }
    ];
    extraRustcOpts = rustcOpts ++ ["-C strip=symbols"];
  };

  extraAttrsFor = {
    jcode = binary "jcode";
    jcode-desktop = binary "jcode-desktop";
    jcode-desktop-ui.type = ["lib"];
  };

  workspaceCrateOverride = crate: _attrs:
    {
      src = repoSubset {
        name = "jcode-src-${crate}";
        paths =
          ["Cargo.toml" "Cargo.lock" "${checkoutOf crate}/Cargo.toml"]
          ++ ownPaths.${crate} or [memberDirs.${crate}]
          ++ extraPathsFor.${crate} or [];
      };
      workspace_member = memberDirs.${crate};
      inherit codegenUnits;
      extraRustcOpts = rustcOpts;
    }
    // extraEnvFor.${crate} or {}
    // extraAttrsFor.${crate} or {};

  nativeOverrides = {
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

    yeslogic-fontconfig-sys = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config];
      buildInputs = [pkgs.fontconfig];
    };

    jcode-tui-mermaid = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config];
      buildInputs = [pkgs.fontconfig];
    };

    jcode-notify-email = _attrs: {
      nativeBuildInputs = [pkgs.pkg-config];
      buildInputs = [pkgs.openssl];
    };

    jcode = _attrs: {
      buildInputs = [pkgs.openssl] ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux [pkgs.libxcb pkgs.alsa-lib];
    };

    jcode-desktop = _attrs: {
      buildInputs = [pkgs.libxcb pkgs.libxkbcommon pkgs.alsa-lib pkgs.fontconfig pkgs.freetype];
    };
  };

  crateOverrides =
    nativeOverrides
    // lib.mapAttrs (crate: _: attrs:
      workspaceCrateOverride crate attrs
      // lib.optionalAttrs (nativeOverrides ? ${crate}) (nativeOverrides.${crate} attrs))
    memberDirs;

  buildRustCrateForPkgs = p:
    p.buildRustCrate.override {
      defaultCrateOverrides = pkgs.defaultCrateOverrides // crateOverrides;
    };

  cargoNix = import ./Cargo.nix {
    inherit pkgs buildRustCrateForPkgs;
    release = true;
  };

  inherit (cargoNix) internal workspaceMembers;

  umbrella = "nix-build-roots";

  crateConfigs =
    internal.crates
    // {
      ${umbrella} = {
        crateName = umbrella;
        version = "0.0.0";
        edition = "2021";
        dependencies =
          lib.mapAttrsToList (crate: root: {
            name = crate;
            inherit (workspaceMembers.${crate}) packageId;
            inherit (root) features;
            usesDefaultFeatures = root.defaultFeatures;
          })
          roots;
      };
    };

  built = internal.builtRustCratesWithFeatures {
    inherit crateConfigs;
    packageId = umbrella;
    features = [];
    runTests = false;
    buildRustCrateForPkgsFunc = buildRustCrateForPkgs;
  };
in
  built.crates.${workspaceMembers.${target}.packageId}.overrideAttrs {inherit name;}

{
  lib,
  stdenv,
  stdenvNoCC,
  rustPlatform,
  fetchurl,
  fetchFromGitHub,
  writeText,
  makeWrapper,
  makeDesktopItem,
  copyDesktopItems,
  autoPatchelfHook,
  pkgs,
  nodejs,
  python3,
  asar,
  p7zip,
  gnugrep,
  coreutils,
  gawk,
  dbus,
  systemdLibs,
  util-linux,
  xdg-utils,
  runtimeShell,
  wl-clipboard,
  xclip,
  xsel,
  src,
}: let
  pin = builtins.readFile (src + "/scripts/setup/installer-pin.sh");
  pinned = name: builtins.head (builtins.match ".*\n${name}='([^']*)'\n.*" pin);

  version = pinned "WISPR_VERSION";
  wmClass = "wispr-flow";

  upstreamNix = builtins.readFile (src + "/nix/wispr-flow.nix");
  upstreamField = name: let
    found = builtins.match ".*helperSrc = fetchFromGitHub \\{[^}]*${name} = \"([^\"]*)\";.*" upstreamNix;
  in
    if found == null
    then throw "wispr-flow: cannot find the helper ${name} in wispr-flow-linux's nix/wispr-flow.nix"
    else builtins.head found;

  helperTag = lib.trim (builtins.readFile (src + "/helper-version.txt"));
  helperSrc =
    if upstreamField "rev" != helperTag
    then throw "wispr-flow: helper-version.txt pins ${helperTag} but nix/wispr-flow.nix fetches ${upstreamField "rev"}"
    else
      fetchFromGitHub {
        owner = "wispr-flow-linux";
        repo = "helper";
        rev = helperTag;
        hash = upstreamField "hash";
      };

  buildLinux = builtins.readFile (src + "/scripts/build-linux.sh");
  electronMajor = builtins.head (builtins.match ".*\nELECTRON_MAJOR=\"\\$\\{ELECTRON_MAJOR:-([0-9]+)}\".*" buildLinux);
  electron = pkgs."electron_${electronMajor}" or (throw "wispr-flow: Wispr Flow now needs Electron ${electronMajor}, which this nixpkgs does not have");

  installer = fetchurl {
    name = "wispr-flow-setup-${version}.exe";
    url = pinned "WISPR_INSTALLER_URL";
    sha256 = pinned "WISPR_INSTALLER_SHA256";
  };

  helper = rustPlatform.buildRustPackage {
    pname = "wispr-flow-linux-helper";
    version = lib.removePrefix "v" helperTag;
    src = helperSrc;
    cargoLock.lockFile = helperSrc + "/Cargo.lock";
    doCheck = false;
    meta = {
      description = "Clean-room Linux helper for Wispr Flow (text injection, focus, push-to-talk)";
      homepage = "https://github.com/wispr-flow-linux/helper";
      license = lib.licenses.unlicense;
      mainProgram = "wispr-flow-linux-helper";
      platforms = lib.platforms.linux;
    };
  };

  npmLock = (lib.importJSON (src + "/scripts/native-modules/package-lock.json")).packages;
  npmTarball = name:
    fetchurl {
      url = npmLock."node_modules/${name}".resolved;
      hash = npmLock."node_modules/${name}".integrity;
    };
  sqlite3Version = npmLock."node_modules/sqlite3".version;
  nodeGyp = "${nodejs}/lib/node_modules/npm/node_modules/node-gyp/bin/node-gyp.js";
  node_sqlite3 = stdenv.mkDerivation {
    pname = "node-sqlite3-electron";
    version = "${sqlite3Version}-electron${electron.version}";

    src = npmTarball "sqlite3";
    nodeAddonApi = npmTarball "node-addon-api";

    nativeBuildInputs = [nodejs python3];

    env = {
      LDFLAGS = "-Wl,-Bsymbolic -Wl,--exclude-libs,ALL";
      npm_config_nodedir = electron.headers;
    };

    postUnpack = ''
      mkdir -p "$sourceRoot/node_modules/node-addon-api"
      tar xzf "$nodeAddonApi" --strip-components=1 -C "$sourceRoot/node_modules/node-addon-api"
    '';

    postPatch = ''
      cat > deps/extract.js <<'EOF'
      const { execFileSync } = require("child_process");
      execFileSync("tar", ["xzf", process.argv[2], "-C", process.argv[3]], { stdio: "inherit" });
      EOF
    '';

    configurePhase = ''
      runHook preConfigure
      export HOME=$TMPDIR
      ${nodeGyp} configure -- -Dnapi_build_version=6
      runHook postConfigure
    '';

    buildPhase = ''
      runHook preBuild
      ${nodeGyp} build -j $NIX_BUILD_CORES
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      install -Dm755 build/Release/node_sqlite3.node $out/node_sqlite3.node
      runHook postInstall
    '';

    doInstallCheck = true;
    installCheckPhase = ''
      runHook preInstallCheck
      export HOME=$TMPDIR
      install -Dm755 $out/node_sqlite3.node build/Release/node_sqlite3.node
      echo 'module.exports = require("../build/Release/node_sqlite3.node");' > lib/sqlite3-binding.js
      bundled=$(sed -n "s/.*'sqlite_version%':'\([0-9]*\)'.*/\1/p" deps/common-sqlite.gypi)
      export EXPECTED_SQLITE="$((10#''${bundled:0:1})).$((10#''${bundled:1:2})).$((10#''${bundled:3:2}))"
      ELECTRON_RUN_AS_NODE=1 ${electron}/bin/electron -e '
        const sqlite3 = require("./lib/sqlite3.js");
        if (sqlite3.VERSION !== process.env.EXPECTED_SQLITE) {
          console.error("addon resolved sqlite " + sqlite3.VERSION + " instead of its bundled " + process.env.EXPECTED_SQLITE);
          process.exit(1);
        }
        const db = new sqlite3.Database(":memory:");
        db.exec("create virtual table t using fts5(x); insert into t values (1)", (e) => {
          if (e) { console.error(e); process.exit(1); }
          db.get("select sqlite_version() v, count(*) n from t", (e, row) => {
            if (e || row.n !== 1) { console.error(e, row); process.exit(1); }
            console.log("node_sqlite3", row.v, "works under electron", process.versions.electron);
          });
        });
      '
      runHook postInstallCheck
    '';
  };

  entryShim = writeText "wispr-flow-entry.js" ''
    "use strict";
    const path = require("path");
    const resources = path.join(__dirname, "..");
    Object.defineProperty(process, "resourcesPath", {
      value: resources,
      enumerable: true,
      configurable: true,
    });
    const { app } = require("electron");
    Object.defineProperty(app, "isPackaged", {
      value: true,
      enumerable: true,
      configurable: true,
    });
    require(path.join(resources, "app.asar"));
  '';

  desktopItem = makeDesktopItem {
    name = "wispr-flow";
    desktopName = "Wispr Flow";
    genericName = "Voice Dictation";
    comment = "Voice dictation that types into your focused app";
    exec = "wispr-flow %U";
    icon = "wispr-flow";
    startupWMClass = wmClass;
    categories = ["Utility" "AudioVideo" "Audio"];
    keywords = ["voice" "dictation" "speech" "transcription"];
    mimeTypes = ["x-scheme-handler/wispr-flow"];
  };

  runtimePath = lib.makeBinPath [wl-clipboard xclip xsel dbus coreutils gawk gnugrep util-linux];
in
  stdenvNoCC.mkDerivation {
    pname = "wispr-flow";
    inherit version src;

    nativeBuildInputs = [
      p7zip
      asar
      nodejs
      python3
      makeWrapper
      copyDesktopItems
      autoPatchelfHook
    ];

    buildInputs = [stdenv.cc.cc.lib systemdLibs];

    desktopItems = [desktopItem];

    postPatch = ''
      patchShebangs scripts
    '';

    buildPhase = ''
      runHook preBuild

      7z x -y ${installer} -oinstaller >/dev/null
      nupkg=$(find installer -iname '*-full.nupkg' | head -1)
      [[ -n $nupkg ]] || { echo "no *-full.nupkg in the installer" >&2; exit 1; }
      7z x -y "$nupkg" -onupkg >/dev/null
      payload=nupkg/lib/net45/resources

      asar extract "$payload/app.asar" contents
      grep -q '"version": "${version}"' contents/package.json \
        || { echo "installer payload is not Wispr Flow ${version}" >&2; exit 1; }
      grep -q '"sqlite3": "${sqlite3Version}"' contents/package.json \
        || { echo "Wispr Flow ${version} no longer bundles sqlite3 ${sqlite3Version}, the rebuilt addon would not match" >&2; exit 1; }
      grep -q '"electron": "${electronMajor}\.' contents/package.json \
        || { echo "Wispr Flow ${version} is not built for Electron ${electronMajor}" >&2; exit 1; }

      (
        source scripts/build-linux.sh
        WORK_DIR=$PWD
        mv contents app.asar.contents
        step3_patch_bundle
        drop_patch_backups "$WORK_DIR/app.asar.contents"
        mv app.asar.contents contents
      )
      python3 ${./warm-deeplink.py} contents/.webpack/main/index.js
      node --check contents/.webpack/main/index.js

      native=contents/.webpack/main/native_modules
      install -m755 ${node_sqlite3}/node_sqlite3.node "$native/build/Release/node_sqlite3.node"
      rm -rf "$native/lib/crypt32-"*.node "$native/jabra-device-connector/win32" \
        "$native/jabra-device-connector/darwin" "$native/roots.exe"
      chmod 755 "$native/jabra-device-connector/linux/jabra-device-connector"

      mkdir -p resources
      asar pack contents resources/app.asar \
        --unpack '*.node' --unpack-dir "''${native#contents/}/jabra-device-connector"
      [[ -x resources/app.asar.unpacked/.webpack/main/native_modules/jabra-device-connector/linux/jabra-device-connector ]] \
        || { echo "jabra-device-connector was not unpacked from the asar" >&2; exit 1; }
      bash scripts/verify-patches.sh resources/app.asar

      for item in "$payload"/*; do
        case "''${item##*/}" in
          app.asar | app.asar.unpacked | Release) ;;
          *) cp -r "$item" resources/ ;;
        esac
      done
      install -Dm755 ${helper}/bin/wispr-flow-linux-helper resources/Release/wispr-flow-linux-helper
      install -Dm644 ${entryShim} resources/entry/index.js
      node -e '
        const fs = require("fs");
        const app = JSON.parse(fs.readFileSync("contents/package.json", "utf8"));
        const entry = {
          name: app.name,
          productName: app.productName,
          version: app.version,
          desktopName: "${wmClass}.desktop",
          main: "index.js",
        };
        fs.writeFileSync("resources/entry/package.json", JSON.stringify(entry, null, 2));
      '

      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall

      lib=$out/lib/wispr-flow
      mkdir -p $lib
      cp -r resources $lib/resources
      install -Dm644 scripts/launcher-common.sh $lib/launcher-common.sh
      install -Dm644 scripts/doctor.sh $lib/doctor.sh

      makeWrapper ${electron}/bin/electron $lib/wispr-flow-electron \
        --add-flags $lib/resources/entry \
        --prefix PATH : ${runtimePath} \
        --set-default CHROME_DESKTOP wispr-flow.desktop

      install -Dm755 ${./launcher.sh} $out/bin/wispr-flow
      substituteInPlace $out/bin/wispr-flow \
        --subst-var-by shell ${runtimeShell} \
        --subst-var-by lib $lib \
        --subst-var-by resources $lib/resources \
        --subst-var-by runtimePath ${runtimePath} \
        --subst-var-by xdgMime ${xdg-utils}/bin/xdg-mime \
        --subst-var-by electronBinary ${electron.unwrapped}/libexec/electron/electron \
        --subst-var-by electronWrapper $lib/wispr-flow-electron \
        --subst-var-by version ${version}

      install -Dm644 resources/assets/logos/wispr-logo.png \
        $out/share/icons/hicolor/256x256/apps/wispr-flow.png
      install -Dm644 resources/assets/logos/wispr-flow.svg \
        $out/share/icons/hicolor/scalable/apps/wispr-flow.svg

      install -Dm644 /dev/stdin $out/lib/udev/rules.d/70-wispr-flow-uinput.rules <<'EOF'
      KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", TAG+="uaccess", GROUP="input", MODE="0660"
      SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", GROUP="input", MODE="0660"
      EOF

      runHook postInstall
    '';

    passthru = {inherit helper node_sqlite3 installer electron;};

    meta = {
      description = "Wispr Flow voice dictation, repackaged from the Windows installer (unofficial)";
      homepage = "https://github.com/wispr-flow-linux/wispr-flow-linux";
      license = lib.licenses.unfree;
      sourceProvenance = [lib.sourceTypes.binaryBytecode lib.sourceTypes.binaryNativeCode];
      mainProgram = "wispr-flow";
      platforms = ["x86_64-linux"];
    };
  }

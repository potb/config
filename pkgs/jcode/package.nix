{
  lib,
  pkgs,
  drowse,
  src,
  desktopSrc,
  patches ? [],
  optLevel ? 1,
  codegenUnits ? 16,
  rootFeatures ? ["pdf" "embeddings"],
}: let
  features = import ../../shared/nix-features.nix;

  patchedSrc =
    if patches == []
    then src
    else
      pkgs.applyPatches {
        name = "jcode-source-patched";
        inherit src patches;
      };

  manifestOf = tree: lib.importTOML (tree + "/Cargo.toml");
  version = (manifestOf src).package.version;
  desktopVersion = (manifestOf desktopSrc).package.version;

  requiredFeatures = ["ca-derivations" "dynamic-derivations" "recursive-nix"];
  missingFeatures = lib.subtractLists features.dynamic requiredFeatures;

  minimumNix = "2.28";
  reviewNix = "2.36";

  compat = import ./compat.nix {inherit lib src desktopSrc;};

  vendorFor = tree: hashes:
    pkgs.rustPlatform.importCargoLock {
      lockFile = tree + "/Cargo.lock";
      outputHashes = lib.importJSON hashes;
    };

  jcodeVendor = vendorFor src ./git-hashes.json;
  desktopVendor = vendorFor desktopSrc ./desktop-git-hashes.json;

  python = pkgs.python3.withPackages (p: [p.tomlkit]);

  nixpkgsPath = let
    path = toString pkgs.path;
  in
    if lib.isStorePath path
    then builtins.appendContext path {${path}.path = true;}
    else "${pkgs.path}";

  graph = pkgs.stdenvNoCC.mkDerivation {
    name = "jcode-graph-${version}-desktop-${desktopVersion}";
    dontUnpack = true;
    dontConfigure = true;
    dontFixup = true;
    nativeBuildInputs = [pkgs.cargo pkgs.crate2nix pkgs.rsync python];
    buildPhase = ''
      runHook preBuild
      mkdir -p $out
      rsync -a \
        --exclude=/assets/demos --exclude=/assets/readme --exclude='/assets/*.png' \
        --exclude=/ios --exclude=/telemetry-worker --exclude=/target \
        ${patchedSrc}/ $out/jcode/
      rsync -a --exclude=/target ${desktopSrc}/ $out/jcode-desktop/
      chmod -R u+w $out
      rm -f $out/jcode/Cargo.lock $out/jcode-desktop/Cargo.lock
      python3 ${./combine-workspace.py} $out jcode jcode-desktop
      mkdir align
      export CARGO_HOME=$PWD/align/cargo-home
      python3 ${./align-lock.py} ${jcodeVendor} ${desktopVendor} $out $PWD/align
      cp align/alignment.json $out/alignment.json
      python3 ${./members.py} $out $out/members.json
      cp ${./crate-hashes.json} $out/crate-hashes.json
      chmod u+w $out/crate-hashes.json
      (cd $out && crate2nix generate -f Cargo.toml -o Cargo.nix -h crate-hashes.json)
      cp ${./dyn.nix} $out/dyn.nix
      runHook postBuild
    '';
  };

  roots =
    {
      jcode = {
        features = rootFeatures;
        defaultFeatures = false;
      };
    }
    // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
      jcode-desktop = {
        features = [];
        defaultFeatures = true;
      };
    };

  generatorFor = target: name:
    (drowse.instantiate {
      inherit name;
      src = graph;
      expr = builtins.readFile ./instantiate.nix;
      passAsFile = ["jcodeSettings"];
      jcodeSettings = builtins.toJSON {
        inherit optLevel codegenUnits name target roots desktopVersion;
      };
      env.NIX_PATH = "nixpkgs=${nixpkgsPath}";
    })
    .drv;

  realise = generator: name: meta:
    pkgs.runCommand name {
      passthru = {inherit generator graph;};
      inherit meta;
    } ''ln -s ${builtins.outputOf "${generator}" "out"} "$out"'';

  jcodeGenerator = generatorFor "jcode" "jcode-${version}";
  desktopGenerator = generatorFor "jcode-desktop" "jcode-desktop-unwrapped-${desktopVersion}";
in
  assert missingFeatures
  == []
  || throw "pkgs/jcode needs the nix experimental features ${lib.concatStringsSep ", " missingFeatures}, which shared/nix-features.nix no longer declares. Either restore them or replace this package with a build that does not generate its derivation graph at build time. See docs/jcode.md.";
  assert lib.versionAtLeast builtins.nixVersion minimumNix
  || throw "pkgs/jcode needs nix ${minimumNix} or newer for dynamic derivations, found ${builtins.nixVersion}.";
  assert lib.versionOlder builtins.nixVersion reviewNix
  || throw "nix ${builtins.nixVersion} reached ${reviewNix}, where dynamic derivations may be stable and builder-rpc-v0 available. Revisit pkgs/jcode before raising this bound: the recursive-nix dependency and the crate2nix generator may both be replaceable. See docs/jcode.md.";
  assert compat.check; {
    jcode =
      (realise jcodeGenerator "jcode-${version}" {
        description = "Coding agent using Claude Max or ChatGPT Pro subscriptions";
        mainProgram = "jcode";
      })
      .overrideAttrs (old: {
        inherit version;
        passthru = old.passthru // {src = patchedSrc;};
      });
    jcode-desktop-unwrapped =
      (realise desktopGenerator "jcode-desktop-unwrapped-${desktopVersion}" {
        description = "Jcode Desktop binary built from the shared per-crate graph";
        mainProgram = "jcode-desktop";
        platforms = lib.platforms.linux;
      })
      .overrideAttrs {version = desktopVersion;};
    inherit graph compat;
  }

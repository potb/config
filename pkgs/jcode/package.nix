{
  lib,
  pkgs,
  drowse,
  src,
  optLevel ? 1,
  codegenUnits ? 16,
  rootFeatures ? ["pdf" "embeddings"],
}: let
  features = import ../../shared/nix-features.nix;

  version = (builtins.fromTOML (builtins.readFile (src + "/Cargo.toml"))).package.version;
  name = "jcode-${version}";

  requiredFeatures = ["ca-derivations" "dynamic-derivations" "recursive-nix"];
  missingFeatures = lib.subtractLists features.dynamic requiredFeatures;

  minimumNix = "2.28";
  reviewNix = "2.36";

  settings = builtins.toJSON {
    inherit optLevel codegenUnits rootFeatures name;
  };

  cargoDeps = pkgs.rustPlatform.importCargoLock {
    lockFile = src + "/Cargo.lock";
    outputHashes = {
      "agentgrep-0.1.6" = "0i9xxsv60xd0wgi47njpvkzvp4jy83cjwil63m9ljwbshvcyq4n8";
      "mermaid-rs-renderer-0.3.1" = "1nsbw3kkfchsb10ki92bjq1b764lj8m3xf5z7w7x1xbmybb23sdr";
    };
  };

  generator =
    (drowse.crate2nix {
      pname = "jcode";
      inherit version src;
      dynamicCargoDeps = false;
      preBuild = ''
        cp ${./crate-hashes.json} crate-hashes.json
        chmod +w crate-hashes.json
      '';
    })
    .drv
    .overrideAttrs {
      inherit cargoDeps;
      instantiateExpr = builtins.readFile ./dyn.nix;
      passAsFile = ["instantiateExpr" "jcodeSettings"];
      jcodeSettings = settings;
    };
in
  assert missingFeatures
  == []
  || throw "pkgs/jcode needs the nix experimental features ${lib.concatStringsSep ", " missingFeatures}, which shared/nix-features.nix no longer declares. Either restore them or replace this package with a build that does not generate its derivation graph at build time. See docs/jcode.md.";
  assert lib.versionAtLeast builtins.nixVersion minimumNix
  || throw "pkgs/jcode needs nix ${minimumNix} or newer for dynamic derivations, found ${builtins.nixVersion}.";
  assert lib.versionOlder builtins.nixVersion reviewNix
  || throw "nix ${builtins.nixVersion} reached ${reviewNix}, where dynamic derivations may be stable and builder-rpc-v0 available. Revisit pkgs/jcode before raising this bound: the recursive-nix dependency and the crate2nix generator may both be replaceable. See docs/jcode.md.";
    pkgs.runCommand name {
      inherit version;
      passthru = {inherit generator;};
      meta = {
        description = "Coding agent using Claude Max or ChatGPT Pro subscriptions";
        mainProgram = "jcode";
      };
    } ''ln -s ${builtins.outputOf "${generator}" "out"} "$out"''

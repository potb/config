{
  lib,
  pkgs,
  src,
  optLevel ? 1,
  codegenUnits ? 16,
}: let
  repoSubset = import ./repo-subset.nix {inherit lib;} src;

  crateNames =
    builtins.attrNames
    (import ./Cargo.nix {
      inherit pkgs;
      buildRustCrateForPkgs = _: _: null;
    }).workspaceMembers;

  cargoNix = import ./Cargo.nix {
    inherit pkgs;
    release = true;
    rootFeatures = ["default"];
    buildRustCrateForPkgs = p:
      p.buildRustCrate.override {
        defaultCrateOverrides =
          pkgs.defaultCrateOverrides
          // (import ./crate-overrides.nix {
            inherit lib pkgs repoSubset optLevel codegenUnits;
            workspaceCrates = crateNames;
          });
      };
  };
in
  cargoNix.workspaceMembers."jcode".build

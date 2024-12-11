{
  lib,
  config,
  inputs,
  pkgs,
  ...
}: {
  nix = let
    flakeInputs = lib.filterAttrs (_: lib.isType "flake") inputs;
  in {
    settings =
      {
        experimental-features = "nix-command flakes pipe-operators";
        warn-dirty = false;
      }
      // (
        if pkgs.stdenv.isDarwin
        then {
          max-jobs = "auto";
          cores = 0;
          upgrade-nix-store-path-url = "https://install.determinate.systems/nix-upgrade/stable/universal";
          trusted-users = ["@admin"];
        }
        else {
          auto-optimise-store = true;
          trusted-users = ["root" "@wheel"];
          flake-registry = "";
          nix-path = config.nix.nixPath;
        }
      );

    package = pkgs.nixVersions.latest;

    channel.enable = !pkgs.stdenv.isDarwin;
    optimise.automatic = pkgs.stdenv.isDarwin;

    registry = lib.mapAttrs (_: flake: {inherit flake;}) flakeInputs;
    nixPath = lib.mapAttrsToList (n: _: "${n}=flake:${n}") flakeInputs;

    gc = lib.mkIf (!pkgs.stdenv.isDarwin) {
      automatic = true;
      dates = "daily";
      options = "--delete-older-than 7d";
    };
  };
}

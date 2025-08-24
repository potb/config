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
    settings = {
      experimental-features = "nix-command flakes pipe-operators";
      warn-dirty = false;
      auto-optimise-store = true;
      trusted-users = ["root" "@admin"];
      flake-registry = "";
      nix-path = config.nix.nixPath;

      substituters = [
        "https://cache.nixos.org"
        "https://potb.cachix.org"
      ];

      trusted-public-keys = [
        "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
        "potb.cachix.org-1:byvGn6qmFOaccjc7kbUMNKLJaCyn/B8HqGNG4gxI6P0="
      ];
    };

    package = pkgs.nixVersions.latest;

    registry = lib.mapAttrs (_: flake: {inherit flake;}) flakeInputs;
    nixPath = lib.mapAttrsToList (n: _: "${n}=flake:${n}") flakeInputs;

    gc = {
      automatic = true;
      interval = {
        Hour = 12;
        Minute = 0;
      };
      options = "--delete-older-than 7d";
    };

    optimise = {
      automatic = true;
      interval = {
        Hour = 12;
        Minute = 30;
      };
    };
  };

  nixpkgs.config.allowUnfree = true;
}
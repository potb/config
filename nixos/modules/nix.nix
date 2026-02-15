{
  lib,
  config,
  inputs,
  pkgs,
  ...
}: {
  nix = let
    flakeInputs = inputs |> lib.filterAttrs (_: lib.isType "flake");
  in {
    settings = {
      experimental-features = "nix-command flakes pipe-operators";
      warn-dirty = false;
      max-jobs = "auto";
      trusted-users = [
        "root"
        "@wheel"
      ];
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

    channel.enable = true;
    optimise.automatic = true;

    registry = flakeInputs |> lib.mapAttrs (_: flake: {inherit flake;});
    nixPath = flakeInputs |> lib.mapAttrsToList (n: _: "${n}=flake:${n}");

    gc = {
      automatic = true;
      dates = "daily";
      options = "--delete-older-than 7d";
    };
  };

  nixpkgs.config.allowUnfree = true;
}

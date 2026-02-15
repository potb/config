{
  lib,
  config,
  inputs,
  pkgs,
  ...
}: {
  # Let Determinate Nix handle Nix configuration management
  determinateNix.enable = true;

  nix = let
    flakeInputs = inputs |> lib.filterAttrs (_: lib.isType "flake");
  in {
    settings = {
      experimental-features = "nix-command flakes pipe-operators";
      warn-dirty = false;
      max-jobs = "auto";
      trusted-users = [
        "root"
        "@admin"
      ];
      substituters = [
        "https://cache.nixos.org"
        "https://potb.cachix.org"
      ];
      trusted-public-keys = [
        "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
        "potb.cachix.org-1:byvGn6qmFOaccjc7kbUMNKLJaCyn/B8HqGNG4gxI6P0="
      ];
      flake-registry = "";
      builders-use-substitutes = true;
    };

    # NOTE: gc and optimise are disabled when using Determinate Nix
    # Determinate Nix manages its own garbage collection and store optimization
    # The nix-darwin module assertions require nix.enable = true, but
    # determinateNix.enable sets nix.enable = false, causing conflicts.
    # These settings are kept commented for documentation but not active.
    #
    # gc = {
    #   automatic = true;
    #   interval = {
    #     Hour = 3;
    #     Minute = 15;
    #     Weekday = 7;
    #   };
    #   options = "--delete-older-than 7d";
    # };
    #
    # optimise.automatic = true;

    registry = flakeInputs |> lib.mapAttrs (_: flake: {inherit flake;});
    nixPath = flakeInputs |> lib.mapAttrsToList (n: _: "${n}=flake:${n}");

    linux-builder.enable = false;

    distributedBuilds = true;
  };

  nixpkgs.config.allowUnfree = true;
}

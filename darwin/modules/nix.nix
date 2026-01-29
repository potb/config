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
    enable = true;
    settings = {
      experimental-features = "nix-command flakes pipe-operators";
      warn-dirty = false;
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

    gc = {
      automatic = true;
      interval = {
        Hour = 3;
        Minute = 15;
        Weekday = 7;
      };
      options = "--delete-older-than 7d";
    };

    optimise.automatic = true;

    registry = flakeInputs |> lib.mapAttrs (_: flake: {inherit flake;});

    # Disable default linux-builder - using nix-rosetta-builder instead
    # nix-rosetta-builder (configured in flake.nix) handles both:
    # - aarch64-linux (native ARM64)
    # - x86_64-linux (via Rosetta 2 acceleration)
    linux-builder.enable = false;

    distributedBuilds = true;
  };

  nixpkgs.config.allowUnfree = true;
}

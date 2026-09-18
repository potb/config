{
  lib,
  inputs,
  pkgs,
  ...
}: let
  features = import ../../shared/nix-features.nix;
  flakeInputs = inputs |> lib.filterAttrs (_: lib.isType "flake");
  nixPath = flakeInputs |> lib.mapAttrsToList (n: _: "${n}=flake:${n}");
in {
  nixos = {
    nix = {
      settings = {
        experimental-features = features.base ++ features.dynamic;
        system-features = [
          "benchmark"
          "big-parallel"
          "kvm"
          "nixos-test"
          "recursive-nix"
        ];
        warn-dirty = false;

        # Keep developer shell build closures warm across the daily GC.
        keep-derivations = true;
        keep-outputs = true;

        # The upstream 1 MiB default can stall high-throughput substitutes.
        download-buffer-size = 512 * 1024 * 1024;

        trusted-users = [
          "root"
          "@wheel"
        ];
        flake-registry = "";
        nix-path = nixPath;

        substituters = [
          "https://cache.nixos.org"
          "https://hyprland.cachix.org"
        ];

        trusted-public-keys = [
          "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
          "hyprland.cachix.org-1:a7pgxzMz7+chwVL3/pzj6jIBMioiJM7ypFP8PwtkuGc="
        ];
        builders-use-substitutes = true;
      };

      channel.enable = true;
      optimise.automatic = true;

      registry = flakeInputs |> lib.mapAttrs (_: flake: {inherit flake;});

      gc = {
        automatic = true;
        dates = "daily";
        options = "--delete-older-than 7d";
      };
    };

    nixpkgs.config.allowUnfree = true;
  };

  darwin = {
    determinateNix = {
      enable = true;
      nixosVmBasedLinuxBuilder.enable = true;
      customSettings = {
        extra-experimental-features = features.base;
        trusted-users = [
          "root"
          "@admin"
        ];
        builders-use-substitutes = true;
      };
    };

    nix = {
      registry = flakeInputs |> lib.mapAttrs (_: flake: {inherit flake;});
      nixPath = flakeInputs |> lib.mapAttrsToList (n: _: "${n}=flake:${n}");
    };

    nixpkgs.config.allowUnfree = true;
  };

  home = {
    # nh reads a flake path per command from the environment. Letting its own
    # module emit those keeps the variable names in one place, and the
    # per-command ones mean `nh os switch` and `nh darwin switch` need no
    # argument on the machine they apply to.
    programs.nh.enable = true;

    linux.programs.nh.osFlake = "/home/potb/projects/potb/config";
    darwin.programs.nh.darwinFlake = "/Users/potb/projects/potb/config";
  };
}

{
  lib,
  config,
  inputs,
  pkgs,
  ...
}: {
  # Let Determinate Nix handle Nix configuration management
  determinateNix = {
    enable = true;
    nixosVmBasedLinuxBuilder.enable = true;
    customSettings = {
      extra-experimental-features = [
        "nix-command"
        "flakes"
        "pipe-operators"
      ];
      trusted-users = [
        "root"
        "@admin"
      ];
      builders-use-substitutes = true;
    };
  };

  nix = let
    flakeInputs = inputs |> lib.filterAttrs (_: lib.isType "flake");
  in {
    registry = flakeInputs |> lib.mapAttrs (_: flake: {inherit flake;});
    nixPath = flakeInputs |> lib.mapAttrsToList (n: _: "${n}=flake:${n}");
  };

  nixpkgs.config.allowUnfree = true;
}

{
  lib,
  config,
  inputs,
  ...
}: {
  nix = let
    flakeInputs = lib.filterAttrs (_: lib.isType "flake") inputs;
  in {
    settings = {
      experimental-features = "nix-command flakes pipe-operators";
      warn-dirty = false;
      auto-optimise-store = true;
      trusted-users = [
        "root"
        "@wheel"
      ];
      flake-registry = "";
      nix-path = config.nix.nixPath;
    };

    channel.enable = false;

    registry = lib.mapAttrs (_: flake: {inherit flake;}) flakeInputs;
    nixPath = lib.mapAttrsToList (n: _: "${n}=flake:${n}") flakeInputs;

    gc = {
      automatic = true;
      dates = "daily";
      options = "--delete-older-than 7d";
    };
  };
}

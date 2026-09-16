{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};

  home.linux = {
    home.packages = with pkgs;
      [
        prismlauncher
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isx86_64 [
        spotify
        discord
      ];
  };
}

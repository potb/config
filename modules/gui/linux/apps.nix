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
        libnotify
        audacity
        prismlauncher
        xarchiver
        rusty-path-of-building
        vlc
        jetbrains.datagrip
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isx86_64 [
        spotify
        slack
        discord
      ];
  };
}

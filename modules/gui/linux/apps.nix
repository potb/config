{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};

  home.linux = {
    home.packages = with pkgs; [
      libnotify
      audacity
      prismlauncher
      xarchiver
      rusty-path-of-building
      vlc
      spotify
      slack
      discord
      jetbrains.datagrip
    ];
  };
}

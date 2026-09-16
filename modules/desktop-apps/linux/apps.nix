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
        xarchiver
        vlc
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isx86_64 [
        slack
      ];
  };
}

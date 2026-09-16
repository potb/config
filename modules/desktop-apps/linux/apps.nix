{pkgs, ...}: {
  nixos = {};
  darwin = {};

  home.linux = {
    home.packages = with pkgs; [
      libnotify
      audacity
      xarchiver
      vlc
    ];
  };
}

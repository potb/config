{pkgs, ...}: {
  nixos = {};

  darwin = {};

  home = {
    home.packages = [pkgs.jcode-desktop];
  };
}

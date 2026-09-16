{pkgs, ...}: {
  nixos = {};
  darwin = {};

  home.linux = {
    home.packages = [pkgs.prismlauncher];
  };
}

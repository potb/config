{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};
  home = lib.optionalAttrs pkgs.stdenv.isLinux {
    fonts.fontconfig.enable = true;

    home.packages = [
      pkgs.noto-fonts-cjk-sans
    ];
  };
}

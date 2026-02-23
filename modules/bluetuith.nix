{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};
  home = lib.optionalAttrs pkgs.stdenv.isLinux {
    programs.bluetuith.enable = true;
  };
}

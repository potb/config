{
  pkgs,
  lib,
  inputs,
  ...
}: {
  home.linux = {
    pkgs,
    lib,
    inputs,
    ...
  }: let
    fonts = import ../../../shared/fonts.nix {inherit pkgs;};
  in {
    services.dunst = {
      enable = true;
      settings.global.font = lib.mkForce "${fonts.ui.name} ${fonts.sizes.str.small}";
    };
  };
}

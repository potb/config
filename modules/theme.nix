{
  pkgs,
  lib,
  inputs,
  ...
}: let
  fonts = import ../shared/fonts.nix {inherit pkgs;};
  stylixConfig =
    "${pkgs.base16-schemes}/share/themes/catppuccin-latte.yaml"
    |> (theme: {
      enable = true;
      base16Scheme = theme;
      fonts = {
        monospace = fonts.monospace;
        sansSerif = fonts.ui;
        serif = fonts.serif;
        emoji = fonts.emoji;
      };
    });
in {
  nixos = {
    imports = with inputs; [
      stylix.nixosModules.stylix
    ];
    stylix = stylixConfig;
  };

  darwin = {
    imports = with inputs; [
      stylix.darwinModules.stylix
    ];
    stylix = stylixConfig;
  };

  home = {config, ...}: {
    gtk.gtk4.theme = config.gtk.theme;
    manual.manpages.enable = false;
  };
}

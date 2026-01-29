{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../fonts.nix {inherit pkgs;};
in {
  stylix =
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
}

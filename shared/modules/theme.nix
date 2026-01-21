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
      # Note: Version mismatch warning expected - nixpkgs-unstable (26.05) is ahead of Stylix's release cycle
      # This is informational and safe. Ref: https://discourse.nixos.org/t/stylix-and-nixpkgs-version-mismatch/64416
      base16Scheme = theme;

      # Fonts from shared/fonts.nix
      fonts = {
        monospace = fonts.monospace;
        sansSerif = fonts.ui;
        serif = fonts.serif;
        emoji = fonts.emoji;
      };
    });
}

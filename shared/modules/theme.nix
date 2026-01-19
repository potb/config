{
  pkgs,
  lib,
  ...
}: {
  stylix =
    "${pkgs.base16-schemes}/share/themes/catppuccin-latte.yaml"
    |> (theme:
      with pkgs; {
        enable = true;
        # Note: Version mismatch warning expected - nixpkgs-unstable (26.05) is ahead of Stylix's release cycle
        # This is informational and safe. Ref: https://discourse.nixos.org/t/stylix-and-nixpkgs-version-mismatch/64416
        base16Scheme = theme;

        # Unified cross-platform fonts (Darwin + Linux compatible)
        fonts = {
          monospace = {
            package = nerd-fonts.fira-code;
            name = "FiraCode Nerd Font Mono";
          };
          sansSerif = {
            package = dejavu_fonts;
            name = "DejaVu Sans";
          };
          serif = {
            package = liberation_ttf;
            name = "Liberation Serif";
          };
          emoji = {
            package = nerd-fonts.symbols-only;
            name = "Symbols Nerd Font";
          };
        };
      });
}

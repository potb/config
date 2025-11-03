{pkgs, lib, ...}: {
  stylix = with pkgs; let
    theme = "${base16-schemes}/share/themes/catppuccin-latte.yaml";
  in {
    enable = true;
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
  };
}

{
  pkgs,
  ...
}: {
  stylix = with pkgs; let
    theme = "${base16-schemes}/share/themes/catppuccin-latte.yaml";
  in {
    enable = true;
    base16Scheme = theme;
  };
}
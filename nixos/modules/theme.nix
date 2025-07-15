{
  pkgs,
  inputs,
  ...
}: {
  imports = with inputs; [
    stylix.nixosModules.stylix
    catppuccin.nixosModules.catppuccin
  ];

  catppuccin = {
    enable = true;
    flavor = "latte";
  };

  stylix = with pkgs; let
    theme = "${base16-schemes}/share/themes/catppuccin-latte.yaml";
  in {
    enable = true;
    base16Scheme = theme;
  };
}

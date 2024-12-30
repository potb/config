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
    wallpaper = runCommand "image.png" {} ''
      COLOR=$(${yq}/bin/yq -r .palette.base00 ${theme})
      COLOR=$COLOR
      ${imagemagick}/bin/convert -size 2540x1460 xc:$COLOR $out
    '';
  in {
    enable = true;
    image = wallpaper;
    base16Scheme = theme;
  };
}

{
  lib,
  pkgs,
  inputs,
  ...
}: {
  nix.settings = {
    substituters = lib.mkAfter ["https://hyprland.cachix.org"];
    trusted-public-keys = lib.mkAfter [
      "hyprland.cachix.org-1:a7pgxzMz7+chwVL3/pzj6jIBMioiJM7ypFP8PwtkuGc="
    ];
  };

  programs.hyprland = let
    system = pkgs.stdenv.hostPlatform.system;
    hyprland-packages = inputs.hyprland.packages.${system};
  in {
    enable = true;
    package = hyprland-packages.hyprland;
    portalPackage = hyprland-packages.xdg-desktop-portal-hyprland;
  };
}

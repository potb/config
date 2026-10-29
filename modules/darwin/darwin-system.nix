{lib, ...}: {
  home.darwin = {
    home.file."Library/Fonts/.home-manager-fonts-version".enable = lib.mkForce false;

    stylix.targets.xresources.enable = false;
  };
}

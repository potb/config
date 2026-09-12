{pkgs, ...}: {
  home.linux = {
    fonts.fontconfig.enable = true;

    home.packages = [
      pkgs.noto-fonts-cjk-sans
    ];
  };
}

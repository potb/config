{
  lib,
  pkgs,
  inputs,
  ...
}: {
  services.displayManager = {
    autoLogin.enable = true;
    autoLogin.user = "potb";
    defaultSession = "none+i3";
  };

  services.xserver.enable = true;
  services.xserver.excludePackages = [pkgs.xterm];
  services.xserver.desktopManager.xterm.enable = false;
  services.xserver = {
    windowManager.i3 = {
      enable = true;
      package = pkgs.i3-gaps;
      extraPackages = with pkgs; [
        dmenu
        i3status
      ];
    };

    displayManager = {
      lightdm = {
        enable = true;
        greeter.enable = false;
      };
    };

    xkb = {
      layout = "qwerty-fr";

      extraLayouts."qwerty-fr" = let
        qwerty-fr = pkgs.qwerty-fr;
      in {
        description = qwerty-fr.meta.description;
        languages = ["eng"];
        symbolsFile = "${qwerty-fr}/share/X11/xkb/symbols/us_qwerty-fr";
      };
    };
  };
}

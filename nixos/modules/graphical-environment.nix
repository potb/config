{
  lib,
  pkgs,
  inputs,
  ...
}: {
  environment.pathsToLink = [
    "/share/xdg-desktop-portal"
    "/share/applications"
  ];

  services.displayManager = {
    autoLogin.enable = true;
    autoLogin.user = "potb";
    defaultSession = "none+i3";
  };

  services.xserver.enable = true;
  services.xserver.deviceSection = ''
    Option "kmsdev" "/dev/dri/card1"
  '';
  services.xserver.excludePackages = [pkgs.xterm];
  services.xserver.desktopManager.xterm.enable = false;

  services.xserver.autoRepeatDelay = 200;
  services.xserver.autoRepeatInterval = 80;

  services.xserver = {
    windowManager.i3 = {
      enable = true;
      package = pkgs.i3;
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

      extraLayouts."qwerty-fr" =
        pkgs.qwerty-fr
        |> (pkg: {
          description = pkg.meta.description;
          languages = ["eng"];
          symbolsFile = "${pkg}/share/X11/xkb/symbols/us_qwerty-fr";
        });
    };

    serverFlagsSection = ''
      Option "BlankTime" "0"
      Option "StandbyTime" "0"
      Option "SuspendTime" "0"
      Option "OffTime" "0"
      Option "DPMS" "false"
    '';
  };
}

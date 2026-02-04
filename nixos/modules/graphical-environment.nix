{
  lib,
  pkgs,
  inputs,
  ...
}: let
  qwertyFr = pkgs.callPackage ../../pkgs/qwerty-fr/package.nix {};
in {
  environment.pathsToLink = [
    "/share/xdg-desktop-portal"
    "/share/applications"
    "/share/wayland-sessions"
    "/share/xsessions"
  ];

  environment.systemPackages = [qwertyFr];

  environment.sessionVariables = {
    XKB_CONFIG_EXTRA_PATH = "${qwertyFr}/share/X11/xkb";
  };

  xdg.portal.enable = true;

  # Seat management for Wayland compositors
  services.seatd.enable = true;

  # Hyprland (Wayland) with hy3 plugin - use hy3's bundled Hyprland for compatibility
  programs.hyprland = {
    enable = true;
    package = inputs.hy3.inputs.hyprland.packages.${pkgs.system}.hyprland;
    portalPackage = inputs.hy3.inputs.hyprland.packages.${pkgs.system}.xdg-desktop-portal-hyprland;
    xwayland.enable = true;
  };

  # XWayland support (for X11 apps under Hyprland)
  services.xserver = {
    enable = true;
    deviceSection = ''
      Option "kmsdev" "/dev/dri/card1"
    '';
    excludePackages = [pkgs.xterm];
    desktopManager.xterm.enable = false;
    displayManager.lightdm.enable = false;

    # Key repeat (for XWayland apps)
    autoRepeatDelay = 200;
    autoRepeatInterval = 80;

    # XKB layout (used by both X11 and Wayland)
    xkb = {
      layout = "qwerty-fr";

      extraLayouts."qwerty-fr" =
        qwertyFr
        |> (pkg: {
          description = pkg.meta.description;
          languages = ["eng"];
          symbolsFile = "${pkg}/share/X11/xkb/symbols/us_qwerty-fr";
        });
    };

    # Disable screen blanking
    serverFlagsSection = ''
      Option "BlankTime" "0"
      Option "StandbyTime" "0"
      Option "SuspendTime" "0"
      Option "OffTime" "0"
      Option "DPMS" "false"
    '';
  };

  services.greetd = {
    enable = true;
    settings = {
      # Autologin on boot
      initial_session = {
        user = "potb";
        command = "start-hyprland";
      };
      # Manual login after logout
      default_session = {
        user = "greeter";
        command = "${pkgs.tuigreet}/bin/tuigreet --time --remember --sessions /run/current-system/sw/share/wayland-sessions";
      };
    };
  };
}

{
  pkgs,
  lib,
  inputs,
  ...
}: {
  # Cursor theme (works for X11, GTK, and Hyprland)
  home.pointerCursor = {
    name = "DMZ-Black";
    package = pkgs.vanilla-dmz;
    size = 24;
    x11.enable = true;
    gtk.enable = true;
    hyprcursor.enable = true;
  };
  # XDG configuration
  xdg = {
    enable = true;

    mimeApps = {
      enable = true;
      defaultApplications =
        {
          vlc = "vlc.desktop";
          chrome = "google-chrome.desktop";
        }
        |> (apps: {
          "audio/*" = [apps.vlc];
          "video/*" = [apps.vlc];
          "x-scheme-handler/http" = [apps.chrome];
          "x-scheme-handler/https" = [apps.chrome];
          "text/html" = [apps.chrome];
        });
    };

    portal = {
      enable = lib.mkForce true; # Override hyprland module's false when package = null
      extraPortals = [
        pkgs.xdg-desktop-portal-gtk
        # Hyprland portal for screen sharing - must match NixOS version
        inputs.hy3.inputs.hyprland.packages.${pkgs.system}.xdg-desktop-portal-hyprland
      ];
      xdgOpenUsePortal = true;
      config = {
        common = {
          default = [
            "hyprland"
            "gtk"
          ];
          "org.freedesktop.impl.portal.ScreenCast" = ["hyprland"];
          "org.freedesktop.impl.portal.Screenshot" = ["hyprland"];
        };
      };
    };
  };

  programs.waybar = {
    enable = true;
    settings = {
      mainBar = {
        position = "bottom";
        layer = "top";
        height = 32;
        spacing = 8;
        modules-left = ["hyprland/workspaces"];
        modules-center = [];
        modules-right = [
          "tray"
          "custom/i3status"
        ];

        "hyprland/workspaces" = {
          format = "{name}";
          on-click = "activate";
        };

        tray = {
          spacing = 6;
        };

        "custom/i3status" = {
          exec = "i3status";
          return-type = "text";
        };
      };
    };

    style = ''
      * {
        font-family: monospace;
        font-size: 14px;
      }

      window#waybar {
        background: #222222;
        color: #dddddd;
      }

      #workspaces button {
        padding: 0 6px;
        color: #dddddd;
        background: transparent;
        border: none;
      }

      #workspaces button.active {
        background: #4c7899;
        color: #ffffff;
      }

      #tray,
      #custom-i3status {
        padding: 0 6px;
      }
    '';
  };

  # Application launchers and utilities
  programs.rofi.enable = true;
  programs.yazi.enable = true;

  # Notifications
  services.dunst = {
    enable = true;
    settings.global.font = lib.mkForce "Inter 10";
  };
}

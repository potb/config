{
  pkgs,
  lib,
  inputs,
  ...
}: {
  nixos = {
    environment.pathsToLink = [
      "/share/xdg-desktop-portal"
      "/share/applications"
      "/share/wayland-sessions"
      "/share/xsessions"
    ];

    xdg.portal.enable = true;

    services.seatd.enable = true;

    programs.hyprland = {
      enable = true;
      package = inputs.hy3.inputs.hyprland.packages.${pkgs.stdenv.hostPlatform.system}.hyprland;
      portalPackage =
        inputs.hy3.inputs.hyprland.packages.${pkgs.stdenv.hostPlatform.system}.xdg-desktop-portal-hyprland;
      xwayland.enable = true;
    };

    services.xserver = {
      enable = true;
      excludePackages = [pkgs.xterm];
      desktopManager.xterm.enable = false;
      displayManager.lightdm.enable = false;

      autoRepeatDelay = 200;
      autoRepeatInterval = 80;

      xkb = {
        layout = "qwerty-fr";

        extraLayouts."qwerty-fr" =
          pkgs.qwertyFr
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

    services.greetd = {
      enable = true;
      settings = {
        initial_session = {
          user = "potb";
          command = "start-hyprland";
        };
        default_session = {
          user = "greeter";
          command = "${pkgs.tuigreet}/bin/tuigreet --time --remember --sessions /run/current-system/sw/share/wayland-sessions";
        };
      };
    };
  };

  home.linux = {
    pkgs,
    lib,
    inputs,
    ...
  }: {
    home.pointerCursor = {
      enable = true;
      name = "DMZ-Black";
      package = pkgs.vanilla-dmz;
      size = 24;
      x11.enable = true;
      gtk.enable = true;
      hyprcursor.enable = true;
    };

    home.sessionVariables = {
      NIXOS_OZONE_WL = "1";
    };

    home.packages = with pkgs; [
      awww
      grim
      slurp
      wl-clipboard
      i3status
    ];

    xdg = {
      enable = true;

      configFile."i3status/config".text = ''
        general {
          colors = true
          interval = 5
          output_format = "none"
        }

        order += "disk /"
        order += "cpu_usage"
        order += "memory"
        order += "tztime local"

        disk "/" {
          format = "| %used / %total"
        }

        cpu_usage {
          format = "CPU %usage"
        }

        memory {
          format = "MEM %used / %total"
        }

        tztime local {
          format = "%Y-%m-%d %H:%M:%S"
        }
      '';

      mimeApps = {
        enable = true;
        defaultApplications =
          {
            vlc = "vlc.desktop";
            chrome = "google-chrome.desktop";
            archive = "xarchiver.desktop";
          }
          |> (apps: {
            "audio/*" = [apps.vlc];
            "video/*" = [apps.vlc];
            "x-scheme-handler/http" = [apps.chrome];
            "x-scheme-handler/https" = [apps.chrome];
            "text/html" = [apps.chrome];
            # Prism Launcher registers itself for application/zip (it opens
            # modpack zips), and with no other zip handler installed it wins
            # every plain zip too. `associations.removed` alone doesn't fix
            # this: it only prunes Prism from the *candidate* list, and with
            # no candidate left xdg-open falls back to the mimeinfo cache,
            # which still resolves to Prism. A real default has to be set.
            "application/zip" = [apps.archive];
          });
        associations.removed = {
          "application/zip" = ["org.prismlauncher.PrismLauncher.desktop"];
        };
      };

      portal = {
        enable = lib.mkForce true;
        extraPortals = [
          pkgs.xdg-desktop-portal-gtk
          inputs.hy3.inputs.hyprland.packages.${pkgs.stdenv.hostPlatform.system}.xdg-desktop-portal-hyprland
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
  };
}

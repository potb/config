{
  pkgs,
  lib,
  inputs,
  ...
}: {
  home.linux = {
    pkgs,
    lib,
    inputs,
    ...
  }: let
    fonts = import ../../../shared/fonts.nix {inherit pkgs;};
  in {
    stylix.targets.waybar.enable = false;

    programs.waybar = {
      enable = true;
      settings = let
        rightModules = [
          "tray"
          "custom/ip"
          "disk"
          "cpu"
          "memory"
          "clock"
        ];
        sharedModules = {
          "hyprland/workspaces" = {
            format = "{name}";
            on-click = "activate";
          };
          tray = {
            spacing = 10;
            icon-size = 24;
            show-passive-items = true;
          };
          "custom/ip" = {
            exec = "ip -4 -o addr show scope global | awk '{split($4,a,\"/\"); print a[1]}' | head -1";
            interval = 10;
          };
          disk = {
            format = "<span font_features='tnum'>{used}</span>";
            path = "/";
            interval = 30;
          };
          cpu = {
            format = "<span font_features='tnum'>{usage:02}%</span>";
            interval = 5;
          };
          memory = {
            format = "<span font_features='tnum'>{used:0.1f}G</span>";
            interval = 5;
          };
          clock = {
            format = "<span font_features='tnum'>{:%Y-%m-%d %H:%M:%S}</span>";
            interval = 1;
          };
        };
        mkBar = name: height: extra:
          sharedModules
          // {
            inherit name;
            position = "top";
            layer = "top";
            inherit height;
            spacing = 8;
            modules-left = ["hyprland/workspaces"];
            modules-center = [];
            modules-right = rightModules;
          }
          // extra;
      in {
        barA = lib.mkMerge [
          (mkBar "bar-a" 46 {
            modules-left = ["hyprland/workspaces"];
            tray = {
              spacing = 10;
              icon-size = 24;
              show-passive-items = true;
            };
            "custom/ip" = {
              exec = "ip -4 -o addr show scope global | awk '{split($4,a,\"/\"); print a[1]}' | head -1";
              format = "{}";
              interval = 10;
            };
            disk = {
              format = "<span font_features='tnum'>{used}</span>";
              path = "/";
              interval = 30;
            };
            cpu = {
              format = "<span font_features='tnum'>{usage:02}%</span>";
              interval = 5;
            };
            memory = {
              format = "<span font_features='tnum'>{used:0.1f}G</span>";
              interval = 5;
            };
            "custom/date" = {
              exec = "date '+%Y-%m-%d'";
              format = "{}";
              interval = 60;
            };
            modules-right = [
              "tray"
              "custom/ip"
              "disk"
              "cpu"
              "memory"
            ];
            clock = {
              format = "<span font_features='tnum'>{:%H:%M:%S}</span>";
              interval = 1;
            };
          })
          {
            modules-right = lib.mkAfter [
              "custom/date"
              "clock"
            ];
          }
        ];
      };

      style = ''
        * {
          font-family: ${fonts.ui.name}, "${fonts.emoji.name}", "${fonts.monospace.name}", sans-serif;
          min-height: 0;
        }

        /* All bars: transparent background (islands float on top) */
        window {
          background: transparent;
          color: rgba(255, 255, 255, 0.85);
          font-size: 14px;
          font-weight: 500;
        }

        /* ── Shared light Latte surfaces ── */
        #workspaces {
          background: #e6e9ef;
          border: 1px solid #bcc0cc;
          border-radius: 12px;
          margin: 3px 4px;
          padding: 0 4px;
        }

        #workspaces button {
          padding: 0 8px;
          margin: 3px 2px;
          color: #5c5f77;
          background: transparent;
          border: none;
          border-radius: 8px;
          transition: all 0.2s ease;
        }

        #workspaces button.active {
          color: #4c4f69;
          background: #ccd0da;
        }

        #workspaces button:hover {
          color: #4c4f69;
          background: #dce0e8;
        }

        #tray,
        #custom-ip,
        #disk,
        #cpu,
        #memory,
        #custom-date,
        #clock {
          background: #eff1f5;
          border: 1px solid #bcc0cc;
          border-radius: 12px;
          padding: 4px 12px;
          margin: 3px 3px;
          color: #4c4f69;
        }

        #tray > widget {
          margin: 0 3px;
        }

        menu,
        menu * {
          color: #4c4f69;
          font-family: ${fonts.ui.name}, "${fonts.emoji.name}", "${fonts.monospace.name}", sans-serif;
        }

        menu {
          background: #eff1f5;
          border: 1px solid #bcc0cc;
          border-radius: 12px;
          padding: 6px;
        }

        menuitem {
          color: #4c4f69;
          background: transparent;
          border-radius: 8px;
        }

        menuitem:hover,
        menuitem:focus {
          background: #dce0e8;
          color: #4c4f69;
        }

        .bar-a #workspaces,
        .bar-a #tray,
        .bar-a #custom-ip,
        .bar-a #disk,
        .bar-a #cpu,
        .bar-a #memory,
        .bar-a #custom-date,
        .bar-a #clock {
          background: #e6e9ef;
          border: 1px solid #bcc0cc;
          border-radius: 19px;
          margin: 7px 10px;
          padding: 8px 18px;
          box-shadow: 0 8px 18px rgba(76, 79, 105, 0.06);
          font-size: 18px;
          font-weight: 700;
          color: #4c4f69;
        }

        .bar-a #workspaces { background: #dce0e8; padding: 0 11px; }
        .bar-a #workspaces button { color: #5c5f77; background: transparent; padding: 0 12px; margin: 5px 3px; font-size: 18px; font-weight: 700; }
        .bar-a #workspaces button.active { background: #ccd0da; }
        .bar-a #workspaces button:hover { background: #eff1f5; }

      '';
    };
  };
}

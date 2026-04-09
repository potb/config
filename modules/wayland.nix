{
  pkgs,
  lib,
  inputs,
  ...
}: {
  nixos = builtins.seq lib (
    let
      qwertyFr = pkgs.callPackage ../pkgs/qwerty-fr/package.nix {};
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
            qwertyFr
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
    }
  );

  darwin = {};

  home = {
    pkgs,
    lib,
    inputs,
    ...
  }:
    lib.optionalAttrs pkgs.stdenv.isLinux (
      let
        fonts = import ../shared/fonts.nix {inherit pkgs;};

        hy3PluginConf = let
          hy3 = inputs.hy3.packages.${pkgs.stdenv.hostPlatform.system}.hy3;
        in
          pkgs.writeText "hypr-hy3-plugin.conf" "plugin = ${hy3}/lib/libhy3.so";

        brightnessStep = pkgs.writeShellScript "brightness-step" ''
          set -euo pipefail
          DDCUTIL="${pkgs.ddcutil}/bin/ddcutil"
          STEP=10

          BUSES=$($DDCUTIL detect --brief 2>/dev/null | ${pkgs.gnugrep}/bin/grep -oP 'I2C bus:\s+/dev/i2c-\K[0-9]+' || true)
          [ -z "$BUSES" ] && exit 0

          FIRST_BUS=$(echo "$BUSES" | head -1)
          CURRENT=$($DDCUTIL --bus "$FIRST_BUS" getvcp 10 2>/dev/null | ${pkgs.gnugrep}/bin/grep -oP 'current value =\s*\K[0-9]+' || echo "50")

          case "''${1:-}" in
            up)   NEW=$(( CURRENT + STEP > 100 ? 100 : CURRENT + STEP )) ;;
            down) NEW=$(( CURRENT - STEP < 0   ? 0   : CURRENT - STEP )) ;;
            *)    exit 1 ;;
          esac

          for BUS in $BUSES; do
            $DDCUTIL --bus "$BUS" setvcp 10 "$NEW" --noverify &
          done
          wait
        '';
      in {
        home.pointerCursor = {
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

        wayland.windowManager.hyprland = {
          enable = true;

          package = null;
          portalPackage = null;

          settings = {
            source = ["${hy3PluginConf}"];

            monitor = [
              "DP-1, 3840x2160@120, 0x0, 1"
            ];

            workspace = [
              "1, monitor:DP-1, default:true"
            ];

            "$mod" = "SUPER";

            env = [
              "GDK_BACKEND,wayland,x11,*"
              "QT_QPA_PLATFORM,wayland;xcb"

              "MOZ_ENABLE_WAYLAND,1"

              "XDG_CURRENT_DESKTOP,Hyprland"
              "XDG_SESSION_TYPE,wayland"
              "XDG_SESSION_DESKTOP,Hyprland"

              "ELECTRON_OZONE_PLATFORM_HINT,auto"

              "_JAVA_AWT_WM_NONREPARENTING,1"
            ];

            general = {
              gaps_in = 10;
              gaps_out = 5;
              border_size = 4;
              layout = "hy3";
              allow_tearing = false;
            };

            xwayland = {
              force_zero_scaling = true;
            };

            decoration = {
              rounding = 0;

              blur = {
                enabled = true;
                size = 5;
                passes = 3;
                vibrancy = 0.17;
              };
            };

            input = {
              kb_layout = "us_qwerty-fr";
              kb_variant = "qwerty-fr";
              repeat_delay = 200;
              repeat_rate = 80;
              follow_mouse = 1;
            };

            exec-once = [
              "dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE"
              "systemctl --user restart xdg-desktop-portal-hyprland xdg-desktop-portal"

              "systemctl --user start awww-daemon.service"

              "dunst"
              "waybar"
            ];

            bind = [
              "$mod, Return, exec, alacritty"
              "$mod, p, exec, rofi -show drun"
              "$mod, w, exec, google-chrome-stable"

              ", Print, exec, grim -g \"$(slurp)\" - | wl-copy"

              "$mod, BackSpace, hy3:killactive"
              "$mod, f, fullscreen"
              "$mod, space, togglefloating"
              "$mod SHIFT, space, togglefloating"

              "$mod, h, hy3:makegroup, h, ephemeral"
              "$mod, v, hy3:makegroup, v, ephemeral"
              "$mod, t, hy3:makegroup, tab"
              "$mod, s, hy3:changegroup, opposite"

              "$mod SHIFT, r, exec, hyprctl reload"
              "$mod SHIFT, Escape, exit"

              "$mod, Left, hy3:movefocus, l"
              "$mod, Right, hy3:movefocus, r"
              "$mod, Up, hy3:movefocus, u"
              "$mod, Down, hy3:movefocus, d"

              "$mod SHIFT, Left, hy3:movewindow, l"
              "$mod SHIFT, Right, hy3:movewindow, r"
              "$mod SHIFT, Up, hy3:movewindow, u"
              "$mod SHIFT, Down, hy3:movewindow, d"

              "$mod, 1, workspace, 1"
              "$mod, 2, workspace, 2"
              "$mod, 3, workspace, 3"
              "$mod, 4, workspace, 4"
              "$mod, 5, workspace, 5"
              "$mod, 6, workspace, 6"
              "$mod, 7, workspace, 7"
              "$mod, 8, workspace, 8"
              "$mod, 9, workspace, 9"
              "$mod, 0, workspace, 10"

              "$mod SHIFT, 1, hy3:movetoworkspace, 1"
              "$mod SHIFT, 2, hy3:movetoworkspace, 2"
              "$mod SHIFT, 3, hy3:movetoworkspace, 3"
              "$mod SHIFT, 4, hy3:movetoworkspace, 4"
              "$mod SHIFT, 5, hy3:movetoworkspace, 5"
              "$mod SHIFT, 6, hy3:movetoworkspace, 6"
              "$mod SHIFT, 7, hy3:movetoworkspace, 7"
              "$mod SHIFT, 8, hy3:movetoworkspace, 8"
              "$mod SHIFT, 9, hy3:movetoworkspace, 9"
              "$mod SHIFT, 0, hy3:movetoworkspace, 10"

              "$mod CTRL, 1, hy3:movetoworkspace, 1, follow"
              "$mod CTRL, 2, hy3:movetoworkspace, 2, follow"
              "$mod CTRL, 3, hy3:movetoworkspace, 3, follow"
              "$mod CTRL, 4, hy3:movetoworkspace, 4, follow"
              "$mod CTRL, 5, hy3:movetoworkspace, 5, follow"
              "$mod CTRL, 6, hy3:movetoworkspace, 6, follow"
              "$mod CTRL, 7, hy3:movetoworkspace, 7, follow"
              "$mod CTRL, 8, hy3:movetoworkspace, 8, follow"
              "$mod CTRL, 9, hy3:movetoworkspace, 9, follow"
              "$mod CTRL, 0, hy3:movetoworkspace, 10, follow"
            ];

            bindl = [
              ", XF86AudioPrev, exec, ${pkgs.playerctl}/bin/playerctl previous"
              ", XF86AudioPlay, exec, ${pkgs.playerctl}/bin/playerctl play-pause"
              ", XF86AudioNext, exec, ${pkgs.playerctl}/bin/playerctl next"
              ", XF86MonBrightnessUp, exec, ${brightnessStep} up"
              ", XF86MonBrightnessDown, exec, ${brightnessStep} down"
            ];

            bindm = [
              "$mod, mouse:272, movewindow"
              "$mod, mouse:273, resizewindow"
            ];

            plugin.hy3 = {
              no_gaps_when_only = 0;
              node_collapse_policy = 2;
              group_inset = 10;

              tabs = {
                height = 22;
                padding = 6;
                radius = 0;
                border_width = 2;
                render_text = true;
                text_center = true;
                text_font = fonts.ui.name;
                text_height = 8;
              };

              autotile = {
                enable = false;
              };
            };

            misc = {
              force_default_wallpaper = 0;
              disable_hyprland_logo = true;
            };

            windowrule = [
              "match:class ^(jetbrains-.*)$, match:float true, immediate on"
              "size 1 1, move -100 -100, match:xwayland true, match:title ^$, match:class ^$, match:initial_class ^$, match:initial_title ^$"
              "no_anim on, match:class ^(jetbrains-idea)$"
            ];
          };
        };

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
            barA = mkBar "bar-a" 46 {
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
                "custom/date"
                "clock"
              ];
              clock = {
                format = "<span font_features='tnum'>{:%H:%M:%S}</span>";
                interval = 1;
              };
            };
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

        programs.rofi.enable = true;

        systemd.user.services.awww-daemon = {
          Unit = {
            Description = "awww wallpaper daemon";
            PartOf = ["graphical-session.target"];
            After = ["graphical-session.target"];
          };
          Service = {
            ExecStart = "${pkgs.awww}/bin/awww-daemon";
            Restart = "on-failure";
            RestartSec = 5;
          };
          Install.WantedBy = ["graphical-session.target"];
        };

        systemd.user.services.update-nasa-apod-wallpaper = let
          curl = "${pkgs.curl}/bin/curl";
          grep = "${pkgs.gnugrep}/bin/grep";
          sed = "${pkgs.gnused}/bin/sed";
          awww = "${pkgs.awww}/bin/awww";
          hyprctl = "${
            inputs.hy3.inputs.hyprland.packages.${pkgs.stdenv.hostPlatform.system}.hyprland
          }/bin/hyprctl";
          magick = "${pkgs.imagemagick}/bin/magick";
          jq = "${pkgs.jq}/bin/jq";
          script = pkgs.writeShellScript "update-nasa-apod-wallpaper" ''
            set -eu

            IMAGE_DIR="$HOME/Pictures/nasa-apod"
            IMAGE_PATH="$IMAGE_DIR/apod.jpg"
            TEMP_IMAGE_PATH="$IMAGE_DIR/apod_temp.jpg"
            APOD_URL="https://apod.nasa.gov/apod/astropix.html"
            APOD_BASE="https://apod.nasa.gov/apod/"
            BAR_HEIGHT=0

            mkdir -p "$IMAGE_DIR"

            echo "Fetching NASA Astronomy Picture of the Day..."

            RETRY_COUNT=0
            MAX_RETRIES=3
            SUCCESS=false

            while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
              if PAGE_CONTENT=$(${curl} -sL --max-time 15 "$APOD_URL"); then
                IMAGE_REL=$(echo "$PAGE_CONTENT" | ${grep} -oP 'href="image/[^"]+' | head -1 | ${sed} 's/href="//')
                if [ -n "$IMAGE_REL" ]; then
                  SUCCESS=true
                else
                  echo "No image found on page, retrying..."
                  RETRY_COUNT=$((RETRY_COUNT + 1))
                  sleep 5
                fi
              else
                RETRY_COUNT=$((RETRY_COUNT + 1))
                if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                  echo "Page fetch failed, retrying in 5 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
                  sleep 5
                fi
              fi
            done

            if [ "$SUCCESS" = "false" ]; then
              echo "Failed to fetch APOD page after $MAX_RETRIES attempts. Keeping existing wallpaper."
              exit 0
            fi

            IMAGE_URL="$APOD_BASE$IMAGE_REL"
            echo "Image URL: $IMAGE_URL"

            TITLE=$(echo "$PAGE_CONTENT" | ${grep} -oP '(?<=<b>)[^<]+' | head -1 || echo "Unknown")
            echo "Title: $TITLE"

            echo "Downloading image..."

            RETRY_COUNT=0
            SUCCESS=false

            while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = "false" ]; do
              if ${curl} -sL --max-time 60 "$IMAGE_URL" -o "$TEMP_IMAGE_PATH"; then
                SUCCESS=true
              else
                RETRY_COUNT=$((RETRY_COUNT + 1))
                if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                  echo "Image download failed, retrying in 5 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
                  sleep 5
                fi
              fi
            done

            if [ "$SUCCESS" = "false" ]; then
              echo "Failed to download image after $MAX_RETRIES attempts. Keeping existing wallpaper."
              rm -f "$TEMP_IMAGE_PATH"
              exit 0
            fi

            if [ ! -s "$TEMP_IMAGE_PATH" ] || [ "$(wc -c < "$TEMP_IMAGE_PATH")" -lt 1000 ]; then
              echo "Downloaded file is empty or too small. Keeping existing wallpaper."
              rm -f "$TEMP_IMAGE_PATH"
              exit 0
            fi

            mv "$TEMP_IMAGE_PATH" "$IMAGE_PATH"
            echo "Wallpaper updated successfully: $TITLE"

            # Process wallpaper for each monitor, accounting for bar height
            MONITORS=$(${hyprctl} monitors -j 2>/dev/null || echo "[]")
            if [ "$MONITORS" = "[]" ]; then
              echo "No monitors detected, skipping wallpaper set."
              exit 0
            fi

            echo "$MONITORS" | ${jq} -r '.[] | "\(.name) \(.width) \(.height)"' | while read -r MON_NAME MON_W MON_H; do
              VISIBLE_H=$((MON_H - BAR_HEIGHT))
              echo "Processing for $MON_NAME: ''${MON_W}x''${MON_H}, visible area ''${MON_W}x''${VISIBLE_H}"

              PROCESSED_MON="$IMAGE_DIR/apod_processed_$MON_NAME.png"

              # Create black canvas at full monitor resolution, fit image into visible area, center in top portion
              ${magick} "$IMAGE_PATH" \
                -resize "''${MON_W}x''${VISIBLE_H}" \
                -background black \
                -gravity north \
                -extent "''${MON_W}x''${MON_H}" \
                "$PROCESSED_MON"

              echo "Setting wallpaper on $MON_NAME..."
              ${awww} img -o "$MON_NAME" "$PROCESSED_MON" --transition-type fade --transition-duration 2 || echo "awww failed for $MON_NAME"
            done
          '';
        in {
          Unit = {
            Description = "Update NASA Astronomy Picture of the Day Wallpaper";
            After = [
              "awww-daemon.service"
              "network-online.target"
            ];
            Requires = ["awww-daemon.service"];
            Wants = ["network-online.target"];
          };
          Service = {
            Type = "oneshot";
            ExecStart = "${script}";
          };
        };

        systemd.user.timers.update-nasa-apod-wallpaper = {
          Unit.Description = "Update NASA APOD wallpaper hourly";
          Timer = {
            OnCalendar = "hourly";
            OnStartupSec = "2min";
            Persistent = true;
            Unit = "update-nasa-apod-wallpaper.service";
          };
          Install.WantedBy = ["timers.target"];
        };

        services.dunst = {
          enable = true;
          settings.global.font = lib.mkForce "${fonts.ui.name} ${fonts.sizes.str.small}";
        };
      }
    );
}

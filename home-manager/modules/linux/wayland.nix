{
  pkgs,
  lib,
  inputs,
  ...
}: let
  fonts = import ../../../shared/fonts.nix {inherit pkgs;};

  # Bar module CSS selectors that should use monospace font.
  # The global `*` selector uses sans-serif so tray context menus
  # (rendered as separate GTK top-level windows) get a readable font.
  barMonoSelectors = [
    "#workspaces button"
    "#tray"
    "#custom-ip"
    "#custom-i3status"
  ];
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
    swww
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

    plugins = [inputs.hy3.packages.${pkgs.stdenv.hostPlatform.system}.hy3];

    settings = {
      monitor = [
        "DP-2, 2560x1440@165, 0x0, 1"
        "DP-1, 2560x1440@165, 2560x0, 1"
      ];

      workspace = [
        "1, monitor:DP-1, default:true"
        "10, monitor:DP-2, default:true"
      ];

      "$mod" = "SUPER";

      env = [
        "WLR_RENDERER,vulkan"
        "AMD_VULKAN_ICD,RADV"

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
        allow_tearing = true;
      };

      xwayland = {
        force_zero_scaling = true;
      };

      decoration = {
        rounding = 0;
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

        "systemctl --user start swww-daemon.service"

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
        "immediate on, match:class ^(steam)$"
        "immediate on, match:class ^(.*\\.exe)$"
        "size 1 1, move -100 -100, match:xwayland true, match:title ^$, match:class ^$, match:initial_class ^$, match:initial_title ^$"
      ];
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
          "custom/ip"
          "custom/i3status"
        ];

        "hyprland/workspaces" = {
          format = "{name}";
          on-click = "activate";
        };

        tray = {
          spacing = 6;
        };

        "custom/ip" = {
          exec = "ip -4 -o addr show scope global | awk '{split($4,a,\"/\"); print a[1]}' | head -1";
          interval = 10;
        };

        "custom/i3status" = {
          exec = "i3status";
          return-type = "text";
        };
      };
    };

    style = let
      monoRule = builtins.concatStringsSep ",\n      " barMonoSelectors;
    in ''
      * {
        font-family: ${fonts.ui.name}, sans-serif;
        font-size: ${fonts.sizes.str.large}px;
      }

      ${monoRule} {
        font-family: ${fonts.monospace.name}, monospace;
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

  programs.rofi.enable = true;

  systemd.user.services.swww-daemon = {
    Unit = {
      Description = "swww wallpaper daemon";
      PartOf = ["graphical-session.target"];
      After = ["graphical-session.target"];
    };
    Service = {
      ExecStart = "${pkgs.swww}/bin/swww-daemon";
      Restart = "on-failure";
      RestartSec = 5;
    };
    Install.WantedBy = ["graphical-session.target"];
  };

  systemd.user.services.update-nasa-apod-wallpaper = let
    curl = "${pkgs.curl}/bin/curl";
    grep = "${pkgs.gnugrep}/bin/grep";
    sed = "${pkgs.gnused}/bin/sed";
    swww = "${pkgs.swww}/bin/swww";
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
      BAR_HEIGHT=32

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
        ${swww} img -o "$MON_NAME" "$PROCESSED_MON" --transition-type fade --transition-duration 2 || echo "swww failed for $MON_NAME"
      done
    '';
  in {
    Unit = {
      Description = "Update NASA Astronomy Picture of the Day Wallpaper";
      After = [
        "swww-daemon.service"
        "network-online.target"
      ];
      Requires = ["swww-daemon.service"];
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

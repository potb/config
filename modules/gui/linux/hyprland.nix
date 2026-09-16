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
    wayland.windowManager.hyprland = {
      enable = true;
      configType = "hyprlang";

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
          # Disabled: force_zero_scaling triggers a desiredGeometry() bug
          # (hyprwm/Hyprland#13359) causing X11 popup buffers to only
          # partially fill, seen as black/white split boxes in Battle.net
          # (Electron/CEF) dropdown menus. Monitor runs at scale 1 already,
          # so this flag was a no-op for us anyway.
          force_zero_scaling = false;
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
          "$mod, Return, exec, ghostty"
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
          "size 1 1, move -100 -100, match:xwayland true, match:title ^$, match:class ^$, match:initial_class ^$, match:initial_title ^$"
          # Battle.net (Proton non-Steam shortcut) Electron popups render black
          # dropdowns/panels under blur+transparency. Fully opaque, no blur.
          "no_blur on, match:class ^(steam_app_2962204454)$"
          "opaque on, match:class ^(steam_app_2962204454)$"
        ];
      };
    };
  };
}

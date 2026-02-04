{
  pkgs,
  inputs,
  ...
}: {
  home.packages = [pkgs.swww];

  wayland.windowManager.hyprland = {
    enable = true;

    package = null;
    portalPackage = null;

    plugins = [inputs.hy3.packages.${pkgs.system}.hy3];

    settings = {
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

        "swww-daemon && swww img ~/Pictures/nasa-apod/apod.jpg 2>/dev/null || true"

        "dunst"
        "waybar"
      ];

      bind = [
        "$mod, Return, exec, alacritty"
        "$mod, p, exec, rofi -show drun"
        "$mod, w, exec, google-chrome-stable"
        "$mod, e, exec, alacritty -e yazi"

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
          text_font = "monospace";
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
      ];
    };
  };
}

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
    playerctl = "${pkgs.playerctl}/bin/playerctl";
  in {
    xdg.configFile."hypr/hyprland.lua".force = true;

    wayland.windowManager.hyprland = {
      enable = true;
      configType = "lua";

      package = null;
      portalPackage = null;

      plugins = [pkgs.hyprlandPlugins.hy3];

      settings = {
        env = map (pair: {_args = pair;}) [
          ["GDK_BACKEND" "wayland,x11,*"]
          ["QT_QPA_PLATFORM" "wayland;xcb"]

          ["MOZ_ENABLE_WAYLAND" "1"]

          ["XDG_CURRENT_DESKTOP" "Hyprland"]
          ["XDG_SESSION_TYPE" "wayland"]
          ["XDG_SESSION_DESKTOP" "Hyprland"]

          ["ELECTRON_OZONE_PLATFORM_HINT" "auto"]

          ["_JAVA_AWT_WM_NONREPARENTING" "1"]
        ];

        config = {
          general = {
            gaps_in = 10;
            gaps_out = 5;
            border_size = 4;
            layout = "hy3";
            allow_tearing = false;
          };

          xwayland.force_zero_scaling = false;

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

          misc = {
            force_default_wallpaper = 0;
            disable_hyprland_logo = true;
          };

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
        };

        window_rule = [
          {
            match = {
              xwayland = true;
              title = "^$";
              class = "^$";
              initial_class = "^$";
              initial_title = "^$";
            };
            size = "1 1";
            move = "-100 -100";
          }
          {
            match.class = "^(steam_app_2962204454)$";
            no_blur = true;
            opaque = true;
          }
        ];
      };

      extraConfig = ''
        local hy3 = hl.plugin.hy3
        local mod = "SUPER"

        hl.on("hyprland.start", function()
          hl.exec_cmd("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE")
          hl.exec_cmd("systemctl --user restart xdg-desktop-portal-hyprland xdg-desktop-portal")

          hl.exec_cmd("systemctl --user start awww-daemon.service")

          hl.exec_cmd("dunst")
          hl.exec_cmd("waybar")
        end)

        hl.bind(mod .. " + Return", hl.dsp.exec_cmd("ghostty"))
        hl.bind(mod .. " + p", hl.dsp.exec_cmd("rofi -show drun"))
        hl.bind(mod .. " + w", hl.dsp.exec_cmd("google-chrome-stable"))

        hl.bind("Print", hl.dsp.exec_cmd("grim -g \"$(slurp)\" - | wl-copy"))

        hl.bind(mod .. " + BackSpace", hy3.kill_active())
        hl.bind(mod .. " + f", hl.dsp.window.fullscreen())
        hl.bind(mod .. " + space", hl.dsp.window.float({ action = "toggle" }))
        hl.bind(mod .. " + SHIFT + space", hl.dsp.window.float({ action = "toggle" }))

        hl.bind(mod .. " + h", hy3.make_group("h", { ephemeral = true }))
        hl.bind(mod .. " + v", hy3.make_group("v", { ephemeral = true }))
        hl.bind(mod .. " + t", hy3.make_group("tab"))
        hl.bind(mod .. " + s", hy3.change_group("opposite"))

        hl.bind(mod .. " + SHIFT + r", hl.dsp.reload_config())
        hl.bind(mod .. " + SHIFT + Escape", hl.dsp.exit())

        for key, direction in pairs({ Left = "l", Right = "r", Up = "u", Down = "d" }) do
          hl.bind(mod .. " + " .. key, hy3.move_focus(direction))
          hl.bind(mod .. " + SHIFT + " .. key, hy3.move_window(direction))
        end

        for i = 1, 10 do
          local key = i % 10
          hl.bind(mod .. " + " .. key, hl.dsp.focus({ workspace = i }))
          hl.bind(mod .. " + SHIFT + " .. key, hy3.move_to_workspace(tostring(i)))
          hl.bind(mod .. " + CTRL + " .. key, hy3.move_to_workspace(tostring(i), { follow = true }))
        end

        hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("${playerctl} previous"), { locked = true })
        hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("${playerctl} play-pause"), { locked = true })
        hl.bind("XF86AudioNext", hl.dsp.exec_cmd("${playerctl} next"), { locked = true })

        hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
        hl.bind(mod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })
      '';
    };
  };
}

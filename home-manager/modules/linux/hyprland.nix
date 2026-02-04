{
  pkgs,
  inputs,
  ...
}: {
  # swww wallpaper daemon (simpler IPC than hyprpaper 0.8+)
  home.packages = [pkgs.swww];

  # Hyprland window manager (Wayland) with hy3 plugin for i3-like tiling
  wayland.windowManager.hyprland = {
    enable = true;

    # Use Hyprland from NixOS module (set in graphical-environment.nix)
    # Avoids version mismatch between system and home-manager
    package = null;
    portalPackage = null;

    plugins = [inputs.hy3.packages.${pkgs.system}.hy3];

    settings = {
      "$mod" = "SUPER";

      # Environment variables for AMD GPU + Wayland
      env = [
        # AMD GPU - Vulkan renderer (recommended)
        "WLR_RENDERER,vulkan"
        "AMD_VULKAN_ICD,RADV"

        # Toolkit backends (Wayland-first with X11 fallback)
        "GDK_BACKEND,wayland,x11,*"
        "QT_QPA_PLATFORM,wayland;xcb"

        # Firefox native Wayland
        "MOZ_ENABLE_WAYLAND,1"

        # XDG session variables (for portals and desktop detection)
        "XDG_CURRENT_DESKTOP,Hyprland"
        "XDG_SESSION_TYPE,wayland"
        "XDG_SESSION_DESKTOP,Hyprland"

        # Electron apps - prefer Wayland native
        "ELECTRON_OZONE_PLATFORM_HINT,auto"

        # JetBrains IDEs - fix focus issues on tiling WMs
        "_JAVA_AWT_WM_NONREPARENTING,1"
      ];

      # Appearance (matching i3)
      general = {
        gaps_in = 10;
        gaps_out = 5;
        border_size = 4;
        layout = "hy3"; # i3-like manual tiling
        allow_tearing = true; # Reduces input lag for games
      };

      # XWayland settings
      xwayland = {
        force_zero_scaling = true; # Fixes pixelated XWayland games
      };

      decoration = {
        rounding = 0;
      };

      # Input configuration (qwerty-fr layout)
      input = {
        kb_layout = "us_qwerty-fr";
        kb_variant = "qwerty-fr";
        # Match i3's key repeat settings
        repeat_delay = 200;
        repeat_rate = 80;
        follow_mouse = 1;
      };

      # Startup applications
      exec-once = [
        # Portal initialization (required for screenshare)
        # Must export HYPRLAND_INSTANCE_SIGNATURE for xdg-desktop-portal-hyprland
        "dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE"
        # Restart portal to pick up the environment
        "systemctl --user restart xdg-desktop-portal-hyprland xdg-desktop-portal"

        # Wallpaper daemon (swww) - must start before setting wallpaper
        "swww-daemon && swww img ~/Pictures/nasa-apod/apod.jpg 2>/dev/null || true"

        "dunst" # Notifications (works on both X11 and Wayland)
        "waybar" # Status bar (i3status-like)
      ];

      # Keybindings (i3-like with hy3)
      bind = [
        # Applications
        "$mod, Return, exec, alacritty"
        "$mod, p, exec, rofi -show drun"
        "$mod, w, exec, google-chrome-stable"
        "$mod, e, exec, alacritty -e yazi"

        # Screenshot (grim + slurp + wl-copy)
        ", Print, exec, grim -g \"$(slurp)\" - | wl-copy"

        # Window management (hy3)
        "$mod, BackSpace, hy3:killactive"
        "$mod, f, fullscreen"
        "$mod, space, togglefloating"
        "$mod SHIFT, space, togglefloating"

        # Split direction (i3-like manual tiling)
        "$mod, h, hy3:makegroup, h, ephemeral" # Horizontal split
        "$mod, v, hy3:makegroup, v, ephemeral" # Vertical split
        "$mod, t, hy3:makegroup, tab" # Tabbed layout
        "$mod, s, hy3:changegroup, opposite" # Toggle split direction

        # Reload / Exit
        "$mod SHIFT, r, exec, hyprctl reload"
        "$mod SHIFT, Escape, exit"

        # Focus (arrows) - hy3 dispatcher
        "$mod, Left, hy3:movefocus, l"
        "$mod, Right, hy3:movefocus, r"
        "$mod, Up, hy3:movefocus, u"
        "$mod, Down, hy3:movefocus, d"

        # Move windows (arrows) - hy3 dispatcher
        "$mod SHIFT, Left, hy3:movewindow, l"
        "$mod SHIFT, Right, hy3:movewindow, r"
        "$mod SHIFT, Up, hy3:movewindow, u"
        "$mod SHIFT, Down, hy3:movewindow, d"

        # Workspaces 1-10
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

        # Move to workspace (window stays, focus stays)
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

        # Move to workspace and follow
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

      # Mouse bindings for window management
      bindm = [
        "$mod, mouse:272, movewindow" # Left click drag to move
        "$mod, mouse:273, resizewindow" # Right click drag to resize
      ];

      # hy3 plugin configuration
      plugin.hy3 = {
        no_gaps_when_only = 0;
        node_collapse_policy = 2;
        group_inset = 10;

        tabs = {
          height = 22;
          padding = 6;
          radius = 0; # Match i3 square corners
          border_width = 2;
          render_text = true;
          text_center = true;
          text_font = "monospace";
          text_height = 8;
        };

        autotile = {
          enable = false; # Manual tiling like i3
        };
      };

      # Misc settings
      misc = {
        force_default_wallpaper = 0;
        disable_hyprland_logo = true;
      };

      # Window rules for games (tearing for lower latency)
      windowrule = [
        "immediate on, match:class ^(steam)$"
        "immediate on, match:class ^(.*\\.exe)$"
      ];
    };
  };
}

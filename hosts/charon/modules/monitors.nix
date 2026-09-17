{...}: {
  home-manager.users.potb = {
    wayland.windowManager.hyprland.settings = {
      monitor = [
        "DP-1, 3840x2160@120, 0x0, 1"
      ];

      workspace = [
        "1, monitor:DP-1, default:true"
      ];
    };
  };
}

{...}: {
  home-manager.users.potb = {
    wayland.windowManager.hyprland.settings = {
      monitor = [
        {
          output = "DP-1";
          mode = "3840x2160@120";
          position = "0x0";
          scale = 1;
        }
      ];

      workspace_rule = [
        {
          workspace = "1";
          monitor = "DP-1";
          default = true;
        }
      ];
    };
  };
}

{
  lib,
  pkgs,
  ...
}: let
  wispr-flow = lib.optionals (lib.meta.availableOn pkgs.stdenv.hostPlatform pkgs.wispr-flow) [pkgs.wispr-flow];
in {
  nixos = {
    services.udev.packages = wispr-flow;
  };

  darwin = {};

  home.linux = {
    home.packages = wispr-flow;

    xdg.mimeApps.defaultApplications = lib.mkIf (wispr-flow != []) {
      "x-scheme-handler/wispr-flow" = ["wispr-flow.desktop"];
    };

    wayland.windowManager.hyprland.settings.window_rule = lib.optionals (wispr-flow != []) [
      {
        match = {
          class = "^(wispr-flow)$";
          initial_title = "^(Flow Status Indicator)$";
        };
        pin = true;
        no_focus = true;
        no_shadow = true;
        no_blur = true;
        border_size = 0;
      }
    ];
  };
}

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

    wayland.windowManager.hyprland.settings.windowrule = lib.optionals (wispr-flow != []) [
      "pin on, no_focus on, no_shadow on, no_blur on, border_size 0, match:class ^(wispr-flow)$, match:initial_title ^(Flow Status Indicator)$"
    ];
  };
}

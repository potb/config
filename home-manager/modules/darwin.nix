{
  pkgs,
  lib,
  inputs,
  ...
}: {
  stylix.targets.xresources.enable = false;

  # macOS-specific configurations
  home.packages = with pkgs; [
    python3
    google-chrome
    slack
    discord
    jetbrains.webstorm
    bitwarden
    raycast
  ];

  # macOS-specific session variables
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";
  };
}

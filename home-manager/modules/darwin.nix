{
  pkgs,
  lib,
  inputs,
  ...
}: {
  stylix.targets.xresources.enable = false;

  # Font configuration
  fonts.fontconfig.enable = true;
  home.packages = with pkgs; [
    # Font packages
    nerd-fonts.fira-code

    # Applications
    python3
    google-chrome
    slack
    discord
    jetbrains.webstorm
    raycast
  ];

  # macOS-specific session variables
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";
  };
}

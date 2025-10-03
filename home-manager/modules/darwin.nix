{
  pkgs,
  lib,
  inputs,
  ...
}: {
  stylix.targets.xresources.enable = false;

  home.packages = with pkgs; [
    # macOS-specific applications
    raycast
  ];

  # macOS-specific session variables
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";
  };
}

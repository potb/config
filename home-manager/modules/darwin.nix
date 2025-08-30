{
  pkgs,
  lib,
  inputs,
  ...
}: {
  # macOS-specific configurations
  home.packages = with pkgs; [
    # Add macOS-specific packages here as needed
  ];

  # macOS-specific session variables
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";
  };
}

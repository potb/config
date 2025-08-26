{
  pkgs,
  lib,
  ...
}: {
  # macOS-specific configurations can be added here
  # macOS-specific packages
  home.packages = with pkgs; [
    # Add macOS-specific packages here as needed
  ];
}

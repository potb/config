{
  pkgs,
  lib,
  ...
}: {
  # macOS-specific configurations can be added here
  # For now, just basic terminal configuration optimized for macOS
  programs = {
    alacritty = {
      enable = true;

      settings = {
        font = {
          normal = {
            family = lib.mkForce "FiraCode Nerd Font Mono";
            style = "Regular";
          };
          bold = {
            family = lib.mkForce "FiraCode Nerd Font Mono";
            style = "Bold";
          };
          italic = {
            family = lib.mkForce "FiraCode Nerd Font Mono";
            style = "Italic";
          };
          size = lib.mkForce 12.0;
        };
        general = {live_config_reload = true;};
      };
    };
  };

  # macOS-specific packages
  home.packages = with pkgs; [
    # Add macOS-specific packages here as needed
  ];
}
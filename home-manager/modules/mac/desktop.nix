{
  inputs,
  system,
  pkgs,
  lib,
  ...
}: {
  # Mac-specific programs and configurations
  programs = {
    zsh = {
      # Add some macOS-specific shell plugins
      antidote.plugins = [
        "ohmyzsh/ohmyzsh path:plugins/macos"
        "ohmyzsh/ohmyzsh path:plugins/brew"
      ];
    };
  };

  # Mac doesn't need xdg portals or xsession
  # Window management is handled by the system or third-party tools like yabai
}
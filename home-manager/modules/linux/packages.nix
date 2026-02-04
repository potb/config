{
  pkgs,
  lib,
  ...
}: {
  home.sessionVariables = {
    NH_FLAKE = "/home/potb/projects/potb/config";
    # XDG_CURRENT_DESKTOP is set per-session by the window manager
    XDG_DATA_DIRS = "$HOME/Desktop:$XDG_DATA_DIRS";
    # Electron apps: use native Wayland when available
    NIXOS_OZONE_WL = "1";

    # Playwright / agent-browser: use system Google Chrome on NixOS
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
    AGENT_BROWSER_EXECUTABLE_PATH = "${pkgs.google-chrome}/bin/google-chrome-stable";
  };

  # Linux-specific zsh config
  programs.zsh.initContent = lib.mkAfter ''
    unalias l
  '';

  home.packages = with pkgs; [
    # Build tools (Linux-specific: gcc + binutils)
    gcc
    binutils

    # Linux apps
    audacity
    prismlauncher
    vlc
    yazi

    # Wayland tools (for Hyprland session)
    grim # Screenshot
    slurp # Region selection
    wl-clipboard # Clipboard (wl-copy, wl-paste)

    # Status bar
    i3status
  ];
}

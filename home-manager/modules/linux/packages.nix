{
  pkgs,
  lib,
  ...
}: {
  home.sessionVariables = {
    NH_FLAKE = "/home/potb/projects/potb/config";
    NIX_XDG_DESKTOP_PORTAL_DIR = lib.mkForce "/home/potb/.local/state/nix/profiles/home-manager/home-path/share/xdg-desktop-portal/portals";
    XDG_CURRENT_DESKTOP = "i3";
    XDG_DATA_DIRS = "$HOME/Desktop:$XDG_DATA_DIRS";

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
    code-cursor-fhs
    audacity
    maim
    prismlauncher
    vlc
    xclip
    yazi
  ];
}

{
  pkgs,
  lib,
  ...
}: {
  home.sessionVariables = {
    NH_FLAKE = "/home/potb/projects/potb/config";
    XDG_DATA_DIRS = "$HOME/Desktop:$XDG_DATA_DIRS";
    NIXOS_OZONE_WL = "1";

    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
    AGENT_BROWSER_EXECUTABLE_PATH = "${pkgs.google-chrome}/bin/google-chrome-stable";
  };

  programs.zsh.initContent = lib.mkAfter ''
    unalias l
  '';

  home.packages = with pkgs; [
    gcc
    binutils

    audacity
    prismlauncher
    vlc
    yazi

    grim
    slurp
    wl-clipboard

    i3status
  ];
}

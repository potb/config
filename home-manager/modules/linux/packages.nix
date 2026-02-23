{pkgs, ...}: {
  home.sessionVariables = {
    NH_FLAKE = "/home/potb/projects/potb/config";
    XDG_DATA_DIRS = "$HOME/Desktop:$XDG_DATA_DIRS";
  };

  home.packages = with pkgs; [
    gcc
    binutils
    libnotify
    lm_sensors

    audacity
    prismlauncher
    vlc

    spotify
    slack
    discord
    jetbrains.datagrip

    bottles
  ];
}

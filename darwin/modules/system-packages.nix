{pkgs, ...}: {
  fonts.packages = [pkgs.nerd-fonts.fira-code];

  environment.systemPackages = with pkgs; [
    google-chrome
    slack
    discord
    spotify
    audacity
    jetbrains.webstorm
    zed-editor
    bitwarden
  ];
}

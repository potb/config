{
  pkgs,
  inputs,
  ...
}: {
  home = {
    packages = (
      with pkgs; [
        fnm
        act
        duf
        du-dust
        fd
        glow
        httpie
        spotify
        google-chrome
        nh
        nerd-fonts.fira-code
        jetbrains.webstorm
        slack
        discord
        vlc
        audacity
      ]
    );

    sessionVariables = {
      NH_FLAKE = "/home/potb/projects/potb/config";
      EDITOR = "nvim";
      BROWSER = "google-chrome-stable";
    };

    stateVersion = "25.05";
  };
}

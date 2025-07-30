{
  pkgs,
  inputs,
  ...
}: {
  nixpkgs.config.allowUnfree = true;

  programs.home-manager.enable = true;

  home = let
    homePath = "/home/potb";
  in {
    username = "potb";
    homeDirectory = homePath;

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
        bottles
        nerd-fonts.fira-code
        jetbrains.webstorm
        slack
        discord
        maim
        xclip
        vlc
        audacity
      ]
    );

    sessionVariables = {
      NH_FLAKE = "${homePath}/projects/potb/config";
      EDITOR = "nvim";
      BROWSER = "google-chrome-stable";
    };

    stateVersion = "25.05";
  };
}

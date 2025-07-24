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
        inputs."nixpkgs-webstorm".legacyPackages.${pkgs.system}.jetbrains.webstorm
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
    };

    stateVersion = "25.05";
  };
}

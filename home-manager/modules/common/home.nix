{
  pkgs,
  inputs,
  system,
  lib,
  ...
}: let
  homePath = if pkgs.stdenv.isDarwin then "/Users/potb" else "/home/potb";
  browser = if pkgs.stdenv.isDarwin then "open" else "google-chrome-stable";
in {
  nixpkgs.config.allowUnfree = true;

  programs.home-manager.enable = true;

  home = {
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
        nh
        nerd-fonts.fira-code
        vlc
        audacity
      ]
      ++ lib.optionals pkgs.stdenv.isLinux [
        spotify
        google-chrome
        bottles
        jetbrains.webstorm
        slack
        discord
        maim
        xclip
      ]
      ++ lib.optionals pkgs.stdenv.isDarwin [
        # Mac-specific packages (using nixpkgs instead of homebrew)
        spotify
        google-chrome
        slack
        discord
        jetbrains.webstorm
      ]
    );

    sessionVariables = {
      NH_FLAKE = "${homePath}/projects/potb/config";
      EDITOR = "nvim";
      BROWSER = browser;
    };

    stateVersion = "25.05";
  };
}
{
  pkgs,
  inputs,
  lib,
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
        nh
        eza
        bat
        ripgrep
        zoxide
        gh
        jq
        yazi
        colima
        lima
        docker-client
        docker-compose
      ]
    );

    sessionVariables = {
      NH_FLAKE = "/Users/potb/projects/potb/config";
      EDITOR = "nvim";
      BROWSER = "google-chrome";
    };

    stateVersion = "25.05";
  };
}

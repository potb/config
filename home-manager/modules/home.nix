{pkgs, ...}: {
  nixpkgs.config.allowUnfree = true;

  programs.home-manager.enable = true;

  home = let
    homePath = "/home/potb";
  in {
    username = "potb";
    homeDirectory = homePath;

    stateVersion = "25.05";
  };
}

{pkgs, ...}: {
  nixpkgs.config.allowUnfree = true;

  programs.home-manager.enable = true;

  home = let
    homePath =
      if pkgs.stdenv.isDarwin
      then "/Users/potb"
      else "/home/potb";
  in {
    username = "potb";
    homeDirectory = homePath;

    stateVersion = "25.05";
  };
}

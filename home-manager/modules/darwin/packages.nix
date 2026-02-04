{
  pkgs,
  lib,
  ...
}: {
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";

    CC = "${pkgs.stdenv.cc}/bin/cc";
    CXX = "${pkgs.stdenv.cc}/bin/c++";
  };

  home.packages = with pkgs; [
    stdenv.cc

    raycast
  ];
}

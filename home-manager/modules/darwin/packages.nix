{
  pkgs,
  lib,
  ...
}: {
  home.sessionVariables = {
    NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
    BROWSER = lib.mkForce "google-chrome";

    # C/C++ compiler paths for Darwin
    CC = "${pkgs.stdenv.cc}/bin/cc";
    CXX = "${pkgs.stdenv.cc}/bin/c++";
  };

  home.packages = with pkgs; [
    # Darwin-specific build tools
    stdenv.cc

    # macOS apps
    code-cursor
    raycast
  ];
}

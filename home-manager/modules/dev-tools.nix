{
  pkgs,
  lib,
  ...
}: {
  home.packages = with pkgs; [
    (lib.hiPrio clang)
    gnumake
    autoconf
    automake
    libtool
    pkg-config

    fnm
    bun
    uv
    python3

    nixfmt
    python3Packages.black

    awscli2
    stripe-cli
  ];
}

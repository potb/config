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
    deno
    uv
    python3
    python3Packages.pip

    nil
    typescript-language-server
    python3Packages.python-lsp-server

    nixfmt
    python3Packages.black

    awscli2
    stripe-cli
  ];
}

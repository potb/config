{
  pkgs,
  lib,
  ...
}: {
  home.packages = with pkgs; [
    # Build tools (consolidated from linux/darwin)
    (lib.hiPrio clang)
    gnumake
    autoconf
    automake
    libtool
    pkg-config

    # Runtimes
    fnm
    bun
    deno
    uv
    python3
    python3Packages.pip

    # LSPs
    nil
    typescript-language-server
    python3Packages.python-lsp-server

    # Formatters
    nixfmt
    python3Packages.black

    # Cloud tools
    awscli2
    stripe-cli
  ];
}

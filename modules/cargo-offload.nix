{pkgs, ...}: let
  # Cross-compilation, not emulation. rustc emits object code for any target
  # natively, so an aarch64 build here runs at full x86 speed; only the linker
  # has to be target-specific, which is what this wrapper provides. The host's
  # qemu binfmt (see containers.nix) is then needed solely to *run* aarch64
  # test binaries, where it costs roughly an order of magnitude.
  crossCC = pkgs.pkgsCross.aarch64-multiplatform.stdenv.cc;
  crossLinker = "${crossCC}/bin/aarch64-unknown-linux-gnu-gcc";

  # Deliberately nixpkgs' toolchain rather than rustup: both ship a bin/cargo
  # and would collide in systemPackages, and a pinned compiler is what makes an
  # offloaded build reproduce the local one. A checkout that pins a different
  # toolchain should offload through its own `nix develop` instead.
  rustTools = with pkgs; [
    cargo
    rustc
    clippy
    rustfmt
    cargo-nextest
    sccache
    crossCC
  ];

  # Native-link and build-script dependencies. mold is the default linker for
  # host builds because link time dominates incremental rebuilds of large
  # workspaces, which is the case this whole module exists to speed up.
  buildTools = with pkgs; [
    clang
    mold
    pkg-config
    cmake
    gnumake
    perl
    python3
    openssl
    zlib
    sqlite
  ];
in {
  nixos = {
    # In the system closure rather than a per-job `nix shell` so a cold
    # offloaded command compiles immediately instead of substituting first.
    # This is also what puts cargo on the PATH of a non-interactive
    # `ssh charon cargo ...`, which never sources a shell profile.
    environment.systemPackages = rustTools ++ buildTools;
  };

  darwin = {};

  # Cargo has no system-wide config path: it reads $CARGO_HOME/config.toml and
  # then walks up from the invocation directory. So the cross-linker wiring has
  # to live in the user's Cargo home, and an offloaded checkout's own
  # .cargo/config.toml still overrides it.
  home.linux = {
    home.file.".cargo/config.toml".text = ''
      # Managed by potb/config (modules/cargo-offload.nix).

      [target.x86_64-unknown-linux-gnu]
      linker = "${pkgs.clang}/bin/clang"
      rustflags = ["-C", "link-arg=-fuse-ld=${pkgs.mold}/bin/mold"]

      [target.aarch64-unknown-linux-gnu]
      linker = "${crossLinker}"

      # Shared object cache: repeated offloads of the same workspace, and
      # different checkouts of it, reuse each other's compilations.
      [build]
      rustc-wrapper = "${pkgs.sccache}/bin/sccache"

      # 32 threads, minus a couple so the box stays usable as a desktop while
      # a remote job runs.
      jobs = 30

      # The vendored libgit2 fails on private remotes that need the local SSH
      # agent and credential helper; the git CLI already has both.
      [net]
      git-fetch-with-cli = true

      [registries.crates-io]
      protocol = "sparse"
    '';
  };
}

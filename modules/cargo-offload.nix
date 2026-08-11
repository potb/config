{pkgs, ...}: let
  # Cross-compilation, not emulation. rustc emits object code for any target
  # natively, so an aarch64 build here runs at full x86 speed; only the linker
  # has to be target-specific, which is what this wrapper provides. The host's
  # qemu binfmt (see containers.nix) is then needed solely to *run* aarch64
  # test binaries, where it costs roughly an order of magnitude.
  crossCC = pkgs.pkgsCross.aarch64-multiplatform.stdenv.cc;
  crossLinker = "${crossCC}/bin/aarch64-unknown-linux-gnu-gcc";

  # An x86_64-hosted rustc that ships std for *both* targets. Plain pkgs.rustc
  # carries host std only, so `--target aarch64-unknown-linux-gnu` fails with
  # "can't find crate for `std`" and points at a rustup command that does not
  # apply to a Nix-provided toolchain.
  #
  # Offered on PATH rather than pinned through build.rustc, so a checkout that
  # supplies its own toolchain (jcode enters a pinned nightly devshell) still
  # wins; see the Cargo config note below.
  crossRustc = pkgs.pkgsCross.aarch64-multiplatform.buildPackages.rustc;

  # Default toolchain for offloaded jobs that pin nothing themselves.
  # Deliberately nixpkgs' rather than rustup: both ship a bin/cargo and would
  # collide in systemPackages.
  rustTools = with pkgs; [
    cargo
    crossRustc
    clippy
    rustfmt
    cargo-nextest
    sccache
    crossCC
  ];

  # Native-link and build-script dependencies. mold is present because large
  # workspaces spend a large share of an incremental rebuild in the linker, but
  # selecting it is left to each repository: a global host rustflags entry would
  # override the choice for every workspace on the machine.
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
  # then walks up from the invocation directory. So this wiring has to live in
  # the user's Cargo home, where it applies to every offloaded job.
  #
  # Deliberately minimal. A repository that pins its own toolchain (jcode pins a
  # nightly through its flake) must keep winning, and Cargo resolves several of
  # these keys ahead of anything the environment or PATH says:
  #
  #   - build.rustc overrides the compiler on PATH outright, so pinning one here
  #     silently replaces a checkout's pinned toolchain. Verified on charon: a
  #     rustc placed first on PATH was never invoked.
  #   - build.rustc-wrapper likewise forces sccache onto builds that deliberately
  #     avoid it; jcode's dev_cargo.sh disables sccache for incremental profiles
  #     because it cannot cache incremental units.
  #   - build.jobs and a host rustflags entry would similarly override per-repo
  #     choices for every workspace on the machine.
  #
  # What remains is only what a cross build cannot discover for itself.
  home.linux = {
    home.file.".cargo/config.toml".text = ''
      # Managed by potb/config (modules/cargo-offload.nix).

      # rustc emits aarch64 object code natively; only the linker has to be a
      # target one, and it has no default Cargo could infer.
      [target.aarch64-unknown-linux-gnu]
      linker = "${crossLinker}"

      # The vendored libgit2 fails on private remotes that need the local SSH
      # agent and credential helper; the git CLI already has both.
      [net]
      git-fetch-with-cli = true

      [registries.crates-io]
      protocol = "sparse"
    '';
  };
}

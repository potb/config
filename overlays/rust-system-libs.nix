{
  lib,
  inputs,
  ...
}: final: prev: let
  withSystemLibs = attr: package: {
    nativeBuildInputs ? [],
    buildInputs ? [],
  }: let
    upstreamNames = map lib.getName (package.nativeBuildInputs or [] ++ package.buildInputs or []);
    missing = builtins.filter (input: !(builtins.elem (lib.getName input) upstreamNames)) (nativeBuildInputs ++ buildInputs);
  in
    lib.throwIf (missing == [])
    ''
      overlays/rust-system-libs.nix adds ${lib.concatMapStringsSep ", " lib.getName (nativeBuildInputs ++ buildInputs)} to ${attr}
      because nixpkgs' cargo-setup-hook makes *-sys crates link system libraries instead of
      their vendored copies. ${attr} now gets all of them from upstream, so drop its entry.
    ''
    (package.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or []) ++ nativeBuildInputs;
      buildInputs = (old.buildInputs or []) ++ buildInputs;
    }));
in {
  fnm = withSystemLibs "fnm" prev.fnm {
    nativeBuildInputs = [final.pkg-config];
    buildInputs = [final.zstd];
  };

  tectonic-unwrapped = withSystemLibs "tectonic-unwrapped" prev.tectonic-unwrapped {
    buildInputs = [final.aws-lc];
  };

  sem = withSystemLibs "sem" inputs.sem.packages.${final.stdenv.hostPlatform.system}.default {
    buildInputs = [final.zstd final.libgit2 final.sqlite final.zlib];
  };
}

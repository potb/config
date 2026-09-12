{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
  zlib,
}: let
  version = "1.2.0";

  targets = {
    "x86_64-linux" = {
      target = "linux-x64";
      hash = "sha256-ptsNHRP+i+lsqucL0ybvVJejtNPnhjb/glAEaUXDOy0=";
    };
    "aarch64-darwin" = {
      target = "darwin-arm64";
      hash = "sha256-g6Ps3FJEarmmfyqYVg64zcyIHYyuqMBbsqmjgjWWBU0=";
    };
  };

  release =
    targets.${
      stdenv.hostPlatform.system
    }
    or {
      target = "unsupported";
      hash = lib.fakeHash;
    };

  inherit (release) target hash;
in
  stdenv.mkDerivation {
    pname = "codegraph";
    inherit version;

    src = fetchurl {
      url = "https://github.com/colbymchenry/codegraph/releases/download/v${version}/codegraph-${target}.tar.gz";
      inherit hash;
    };

    nativeBuildInputs = lib.optionals stdenv.hostPlatform.isLinux [autoPatchelfHook];
    buildInputs = lib.optionals stdenv.hostPlatform.isLinux [stdenv.cc.cc.lib zlib];

    dontBuild = true;

    installPhase = ''
      runHook preInstall
      mkdir -p $out/libexec/codegraph
      cp -R . $out/libexec/codegraph
      mkdir -p $out/bin
      ln -s $out/libexec/codegraph/bin/codegraph $out/bin/codegraph
      runHook postInstall
    '';

    meta = {
      description = "Pre-indexed code knowledge graph, auto syncs on code changes";
      homepage = "https://github.com/colbymchenry/codegraph";
      mainProgram = "codegraph";
      platforms = builtins.attrNames targets;
    };
  }

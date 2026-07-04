{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
  zlib,
}: let
  version = "1.2.0";
  target =
    {
      "x86_64-linux" = "linux-x64";
      "aarch64-darwin" = "darwin-arm64";
    }
    .${
      stdenv.hostPlatform.system
    }
    or (throw "unsupported system: ${stdenv.hostPlatform.system}");
  hash =
    {
      "x86_64-linux" = "sha256-ptsNHRP+i+lsqucL0ybvVJejtNPnhjb/glAEaUXDOy0=";
      "aarch64-darwin" = "sha256-g6Ps3FJEarmmfyqYVg64zcyIHYyuqMBbsqmjgjWWBU0=";
    }
    .${
      stdenv.hostPlatform.system
    }
    or (throw "unsupported system: ${stdenv.hostPlatform.system}");
in
  stdenv.mkDerivation {
    pname = "codegraph";
    inherit version;

    src = fetchurl {
      url = "https://github.com/colbymchenry/codegraph/releases/download/v${version}/codegraph-${target}.tar.gz";
      inherit hash;
    };

    nativeBuildInputs = lib.optionals stdenv.isLinux [autoPatchelfHook];
    buildInputs = lib.optionals stdenv.isLinux [stdenv.cc.cc.lib zlib];

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
    };
  }

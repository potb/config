{
  stdenvNoCC,
  lib,
  fetchurl,
}:
# MOTIS publishes a statically linked build, so there is nothing to compile:
# the derivation only unpacks the release and puts the binary and its web UI
# where the module expects them.
stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "motis";
  version = "2.11.3";

  src = fetchurl {
    url = "https://github.com/motis-project/motis/releases/download/v${finalAttrs.version}/motis-linux-amd64.tar.bz2";
    hash = "sha256-D/x/wGMwSe28+IFwrAN9JmXOrx8IhKALFfbCuBMTyCU=";
  };

  sourceRoot = ".";
  dontConfigure = true;
  dontBuild = true;
  dontStrip = true;

  installPhase = ''
    runHook preInstall

    install -Dm755 motis $out/bin/motis
    mkdir -p $out/share/motis
    cp -r ui tiles-profiles $out/share/motis/

    runHook postInstall
  '';

  meta = {
    description = "Multimodal routing with real-time public transport, geocoding and tiles";
    homepage = "https://github.com/motis-project/motis";
    changelog = "https://github.com/motis-project/motis/releases/tag/v${finalAttrs.version}";
    license = lib.licenses.mit;
    platforms = ["x86_64-linux"];
    sourceProvenance = [lib.sourceTypes.binaryNativeCode];
    mainProgram = "motis";
  };
})

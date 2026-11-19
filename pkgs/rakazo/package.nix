{
  lib,
  appimageTools,
  fetchurl,
  makeWrapper,
}: let
  pname = "rakazo";
  version = "0.12.0";

  src = fetchurl {
    url = "https://github.com/elie222/rakazo/releases/download/v${version}/Rakazo-${version}.AppImage";
    hash = "sha256-6uhZeW2FgtS0lJU3liuSADvQiSbIuuvQ7iCtbKQcwu0=";
  };

  contents = appimageTools.extractType2 {inherit pname version src;};
in
  appimageTools.wrapType2 {
    inherit pname version src;

    extraPreBwrapCmds = ''
      export RAKAZO_DISABLE_AUTO_UPDATE=1
    '';

    nativeBuildInputs = [makeWrapper];

    extraInstallCommands = ''
      wrapProgram $out/bin/rakazo --add-flags --password-store=gnome-libsecret
      install -Dm444 ${contents}/rakazo.desktop -t $out/share/applications
      substituteInPlace $out/share/applications/rakazo.desktop \
        --replace-fail 'Exec=AppRun --no-sandbox' 'Exec=rakazo'
      install -Dm444 ${contents}/usr/share/icons/hicolor/1024x1024/apps/rakazo.png \
        -t $out/share/icons/hicolor/1024x1024/apps
    '';

    meta = {
      description = "Desktop client that runs a self-hosted Rakazo bot stack on local Docker";
      homepage = "https://github.com/elie222/rakazo";
      license = lib.licenses.asl20;
      sourceProvenance = [lib.sourceTypes.binaryNativeCode];
      platforms = ["x86_64-linux"];
      mainProgram = "rakazo";
    };
  }

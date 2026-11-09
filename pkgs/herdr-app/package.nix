{
  lib,
  stdenvNoCC,
  bash,
  herdr-app,
  herdr-core,
}:
if !stdenvNoCC.hostPlatform.isDarwin
then herdr-app
else
  stdenvNoCC.mkDerivation {
    pname = "herdr-app";
    inherit (herdr-app) version;

    dontUnpack = true;

    installPhase = ''
      runHook preInstall

      app=$out/Applications/Herdr.app
      mkdir -p $app/Contents/MacOS $app/Contents/Resources $out/bin

      cp ${herdr-app}/bin/.herdr-app-wrapped $app/Contents/MacOS/herdr-app

      substitute ${./launcher.sh} $app/Contents/MacOS/Herdr \
        --subst-var-by bash ${bash} \
        --subst-var-by herdrCore ${herdr-core}
      chmod +x $app/Contents/MacOS/Herdr

      substitute ${./Info.plist} $app/Contents/Info.plist \
        --subst-var-by version ${herdr-app.version}

      cp ${herdr-app.src}/assets/icons/Herdr.icns $app/Contents/Resources/
      cp ${herdr-app.src}/LICENSE ${herdr-app.src}/THIRD-PARTY-NOTICES $app/Contents/Resources/

      cat > $out/bin/herdr-app <<EOF
      #!${bash}/bin/bash
      exec "$app/Contents/MacOS/Herdr" "\$@"
      EOF
      chmod +x $out/bin/herdr-app

      runHook postInstall
    '';

    passthru.unwrapped = herdr-app;

    meta =
      herdr-app.meta
      // {
        platforms = lib.platforms.darwin ++ lib.platforms.linux;
      };
  }

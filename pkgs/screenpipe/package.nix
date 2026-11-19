{
  lib,
  stdenvNoCC,
  stdenv,
  fetchurl,
  autoPatchelfHook,
  makeWrapper,
  alsa-lib,
  dbus,
  libgbm,
  libpulseaudio,
  openblas,
  openssl,
  pipewire,
  wayland,
  libxcb,
  xz,
  ffmpeg,
  grim,
  hyprland,
  python3,
  tesseract5,
  npmLatestManifest,
}: let
  npm = lib.importJSON npmLatestManifest;
in
  stdenvNoCC.mkDerivation {
    pname = "screenpipe";
    inherit (npm) version;

    src = fetchurl {
      url = npm.dist.tarball;
      hash = npm.dist.integrity;
    };

    sourceRoot = "package";

    nativeBuildInputs = lib.optionals stdenv.hostPlatform.isLinux [autoPatchelfHook] ++ [makeWrapper];

    buildInputs = lib.optionals stdenv.hostPlatform.isLinux [
      stdenv.cc.cc.lib
      alsa-lib
      dbus
      libgbm
      libpulseaudio
      openblas
      openssl
      pipewire
      wayland
      libxcb
      xz
    ];

    installPhase = ''
      runHook preInstall

      mkdir -p $out/libexec/screenpipe $out/bin
      cp -r bin/. $out/libexec/screenpipe/
      install -Dm644 LICENSE.md -t $out/share/licenses/screenpipe
      ${lib.optionalString stdenv.hostPlatform.isLinux ''
        mv $out/libexec/screenpipe/tesseract $out/libexec/screenpipe/tesseract-real
        install -Dm644 ${./ocrwrap.py} $out/libexec/screenpipe/ocrwrap.py
        install -Dm644 ${tesseract5.languages.fra} $out/libexec/screenpipe/tessdata/fra.traineddata
        makeWrapper ${python3}/bin/python3 $out/libexec/screenpipe/tesseract \
          --add-flags "-I $out/libexec/screenpipe/ocrwrap.py" \
          --set REAL_TESSERACT $out/libexec/screenpipe/tesseract-real \
          --prefix PATH : ${lib.makeBinPath [ffmpeg]}
      ''}

      makeWrapper $out/libexec/screenpipe/screenpipe $out/bin/screenpipe \
        --prefix PATH : $out/libexec/screenpipe \
        --prefix PATH : ${lib.makeBinPath ([ffmpeg] ++ lib.optionals stdenv.hostPlatform.isLinux [grim hyprland])} \
        --set-default TESSDATA_PREFIX $out/libexec/screenpipe/tessdata

      runHook postInstall
    '';

    meta = {
      description = "Records the screen and audio locally and makes them searchable";
      homepage = "https://github.com/screenpipe/screenpipe";
      license = lib.licenses.unfree;
      sourceProvenance = [lib.sourceTypes.binaryNativeCode];
      platforms = ["x86_64-linux" "aarch64-darwin"];
      mainProgram = "screenpipe";
    };
  }

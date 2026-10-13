{
  lib,
  stdenvNoCC,
  makeWrapper,
  patchelf,
  libGL,
  libxkbcommon,
  vulkan-loader,
  wayland,
  poppler-utils,
  src,
  unwrapped,
  jcode,
}:
stdenvNoCC.mkDerivation {
  pname = "jcode-desktop";
  inherit (unwrapped) version;

  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;

  nativeBuildInputs = [makeWrapper patchelf];

  installPhase = ''
    runHook preInstall

    dir=$out/libexec/jcode-desktop
    install -Dm755 ${lib.getExe unwrapped} $dir/jcode-desktop
    ln -s ${lib.getExe jcode} $dir/jcode

    mkdir -p $out/bin
    ln -s $dir/jcode-desktop $out/bin/jcode-desktop

    install -Dm644 ${src}/assets/app-icon/icon-1024.png \
      $out/share/icons/hicolor/1024x1024/apps/jcode-desktop.png
    install -Dm644 /dev/stdin $out/share/applications/jcode-desktop.desktop <<EOF
    [Desktop Entry]
    Type=Application
    Name=Jcode
    Comment=Native desktop client for Jcode
    Exec=$out/bin/jcode-desktop
    Icon=jcode-desktop
    StartupWMClass=jcode-desktop
    Terminal=false
    Categories=Development;Utility;
    StartupNotify=true
    EOF

    runHook postInstall
  '';

  postFixup = ''
    patchelf --add-rpath ${lib.makeLibraryPath [vulkan-loader wayland libGL libxkbcommon]} \
      $out/libexec/jcode-desktop/jcode-desktop

    wrapProgram $out/libexec/jcode-desktop/jcode-desktop \
      --suffix PATH : ${lib.makeBinPath [poppler-utils]} \
      --set-default JCODE_DESKTOP_NO_REDIRECT 1 \
      --set-default JCODE_CHECK_UPDATES false \
      --set-default JCODE_NO_AUTO_UPDATE 1
  '';

  passthru = {inherit jcode unwrapped;};

  meta = {
    description = "Native desktop client for jcode, wired to this repository's jcode build";
    homepage = "https://github.com/1jehuang/jcode-desktop";
    license = lib.licenses.mit;
    mainProgram = "jcode-desktop";
    platforms = lib.platforms.linux;
  };
}

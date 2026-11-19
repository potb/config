{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  systemd,
  hyprland,
}:
stdenvNoCC.mkDerivation {
  pname = "screenpipe-url";
  version = "0.1.0";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [./screenpipe_url.py ./test_screenpipe_url.py];
  };

  nativeBuildInputs = [makeWrapper];
  nativeCheckInputs = [python3];

  dontBuild = true;
  doCheck = true;

  checkPhase = ''
    runHook preCheck
    python3 -B -m unittest test_screenpipe_url
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    install -Dm444 screenpipe_url.py $out/share/screenpipe-url/screenpipe_url.py
    makeWrapper ${lib.getExe python3} $out/bin/screenpipe-url \
      --add-flags "-B $out/share/screenpipe-url/screenpipe_url.py" \
      --prefix PATH : ${lib.makeBinPath [systemd hyprland]}
    runHook postInstall
  '';

  meta = {
    description = "Records the URL of the focused Chrome window through AT-SPI";
    mainProgram = "screenpipe-url";
    platforms = lib.platforms.linux;
  };
}

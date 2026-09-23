{
  lib,
  rustPlatform,
  makeWrapper,
  pkg-config,
  wayland,
  hyprland,
  wtype,
  ydotool,
  grim,
  src,
}:
rustPlatform.buildRustPackage {
  pname = "computer-use-linux";
  version = (lib.importTOML (src + "/Cargo.toml")).package.version;

  inherit src;
  cargoLock.lockFile = src + "/Cargo.lock";

  nativeBuildInputs = [pkg-config makeWrapper];
  buildInputs = [wayland];

  doCheck = false;

  postFixup = ''
    wrapProgram $out/bin/computer-use-linux \
      --suffix PATH : ${lib.makeBinPath [hyprland wtype ydotool grim]}
  '';

  meta = {
    description = "Linux desktop control over MCP: AT-SPI, Wayland/X11 input, screenshots";
    homepage = "https://github.com/agent-sh/computer-use-linux";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "computer-use-linux";
  };
}

{
  lib,
  rustPlatform,
  src,
}:
rustPlatform.buildRustPackage {
  pname = "agent-browser";
  version = (lib.importTOML (src + "/cli/Cargo.toml")).package.version;

  inherit src;
  cargoRoot = "cli";
  buildAndTestSubdir = "cli";
  cargoLock.lockFile = src + "/cli/Cargo.lock";

  doCheck = false;

  meta = {
    description = "Browser automation CLI for AI agents";
    homepage = "https://agent-browser.dev";
    mainProgram = "agent-browser";
  };
}

{
  lib,
  rustPlatform,
  src,
}:
rustPlatform.buildRustPackage {
  pname = "rtk";
  version = (lib.importTOML (src + "/Cargo.toml")).package.version;

  inherit src;

  cargoLock.lockFile = src + "/Cargo.lock";

  doCheck = false;

  meta = {
    description = "CLI proxy that reduces LLM token consumption by 60-90% on common dev commands";
    homepage = "https://github.com/rtk-ai/rtk";
    mainProgram = "rtk";
  };
}

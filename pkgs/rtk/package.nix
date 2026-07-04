{
  rustPlatform,
  src,
}:
rustPlatform.buildRustPackage {
  pname = "rtk";
  version = "0.27.0";

  inherit src;

  cargoLock.lockFile = src + "/Cargo.lock";

  doCheck = false;

  meta = {
    description = "CLI proxy that reduces LLM token consumption by 60-90% on common dev commands";
    homepage = "https://github.com/rtk-ai/rtk";
    mainProgram = "rtk";
  };
}

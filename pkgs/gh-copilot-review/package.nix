{
  buildGoModule,
  src,
}:
buildGoModule {
  pname = "gh-copilot-review";
  version = "unstable";

  inherit src;

  vendorHash = "sha256-7ZkDGa4DdYtnFZad8DfokYW8cPSnaafxti4w9m8AiGM=";

  ldflags = ["-s" "-w"];

  meta = {
    description = "GitHub CLI extension to request GitHub Copilot PR reviews";
    homepage = "https://github.com/k1LoW/gh-copilot-review";
    mainProgram = "gh-copilot-review";
  };
}

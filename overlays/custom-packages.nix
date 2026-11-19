{inputs, ...}: final: _prev: {
  qwertyFr = final.callPackage ../pkgs/qwerty-fr/package.nix {
    src = inputs.qwerty-fr;
  };
  tsm-app = final.callPackage ../pkgs/tsm-app/package.nix {
    src = inputs.tsm-app;
    version = "1.1.15";
  };
  computer-use-linux = final.callPackage ../pkgs/computer-use-linux/package.nix {
    src = inputs.computer-use-linux;
  };
  screenpipe = final.callPackage ../pkgs/screenpipe/package.nix {
    npmLatestManifest =
      if final.stdenv.hostPlatform.system == "aarch64-darwin"
      then inputs.screenpipe-cli-darwin
      else inputs.screenpipe-cli;
  };
  meeting-notes = final.callPackage ../pkgs/meeting-notes/package.nix {};
  meeting-notes-models = final.callPackage ../pkgs/meeting-notes/models.nix {};
  rakazo = final.callPackage ../pkgs/rakazo/package.nix {};
  screenpipe-url = final.callPackage ../pkgs/screenpipe-url/package.nix {};
  herdr-app = final.callPackage ../pkgs/herdr-app/package.nix {
    inherit (inputs.llm-agents.packages.${final.stdenv.hostPlatform.system}) herdr-app herdr-core;
  };
}

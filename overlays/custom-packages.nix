{inputs, ...}: final: _prev: {
  qwertyFr = final.callPackage ../pkgs/qwerty-fr/package.nix {
    src = inputs.qwerty-fr;
  };
  agent-browser = final.callPackage ../pkgs/agent-browser/package.nix {
    src = inputs.agent-browser;
  };
  jcode = final.callPackage ../pkgs/jcode/package.nix {
    pkgs = final;
    src = inputs.jcode;
    patches = [../pkgs/jcode/no-macos-option-char-shortcuts.patch];
    drowse = inputs.drowse.lib.${final.stdenv.hostPlatform.system};
  };
  tsm-app = final.callPackage ../pkgs/tsm-app/package.nix {
    src = inputs.tsm-app;
    version = "1.1.15";
  };
  motis = final.callPackage ../pkgs/motis/package.nix {};
  computer-use-linux = final.callPackage ../pkgs/computer-use-linux/package.nix {
    src = inputs.computer-use-linux;
  };
}

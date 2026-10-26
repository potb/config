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
  wispr-flow = final.callPackage ../pkgs/wispr-flow/package.nix {
    src = inputs.wispr-flow-linux;
  };
}

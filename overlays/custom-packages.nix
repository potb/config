{inputs, ...}: final: _prev: {
  qwertyFr = final.callPackage ../pkgs/qwerty-fr/package.nix {
    src = inputs.qwerty-fr;
  };
  rtk = final.callPackage ../pkgs/rtk/package.nix {
    src = inputs.rtk;
  };
  agent-browser = final.callPackage ../pkgs/agent-browser/package.nix {
    src = inputs.agent-browser;
  };
  tsm-app = final.callPackage ../pkgs/tsm-app/package.nix {
    src = inputs.tsm-app;
    version = "1.1.15";
  };
}

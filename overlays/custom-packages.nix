{inputs, ...}: final: _prev: {
  qwertyFr = final.callPackage ../pkgs/qwerty-fr/package.nix {
    src = inputs.qwerty-fr;
  };
  codegraph = final.callPackage ../pkgs/codegraph/package.nix {};
  rtk = final.callPackage ../pkgs/rtk/package.nix {
    src = inputs.rtk;
  };
}

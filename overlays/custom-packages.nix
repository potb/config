{inputs, ...}: final: _prev: {
  qwertyFr = final.callPackage ../pkgs/qwerty-fr/package.nix {
    src = inputs.qwerty-fr;
  };
  agent-browser = final.callPackage ../pkgs/agent-browser/package.nix {
    src = inputs.agent-browser;
  };
  jcode-build = import ../pkgs/jcode/package.nix {
    inherit (final) lib;
    pkgs = final;
    src = inputs.jcode;
    desktopSrc = inputs.jcode-desktop;
    patches = [
      ../pkgs/jcode/no-macos-option-char-shortcuts.patch
      ../pkgs/jcode/claude-account-auth-lock.patch
      ../pkgs/jcode/keep-swarm-workers-alive.patch
    ];
    drowse = inputs.drowse.lib.${final.stdenv.hostPlatform.system};
  };
  inherit (final.jcode-build) jcode jcode-desktop-unwrapped;
  jcode-desktop = final.callPackage ../pkgs/jcode-desktop/package.nix {
    src = inputs.jcode-desktop;
    unwrapped = final.jcode-desktop-unwrapped;
  };
  tsm-app = final.callPackage ../pkgs/tsm-app/package.nix {
    src = inputs.tsm-app;
    version = "1.1.15";
  };
  motis = final.callPackage ../pkgs/motis/package.nix {};
  computer-use-linux = final.callPackage ../pkgs/computer-use-linux/package.nix {
    src = inputs.computer-use-linux;
  };
  wispr-flow = final.callPackage ../pkgs/wispr-flow/package.nix {
    src = inputs.wispr-flow-linux;
  };
}

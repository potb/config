{inputs, ...}: final: _prev: {
  qwertyFr = final.callPackage ../pkgs/qwerty-fr/package.nix {
    src = inputs.qwerty-fr;
  };
  ghCopilotReview = final.callPackage ../pkgs/gh-copilot-review/package.nix {
    src = inputs.gh-copilot-review;
  };
}

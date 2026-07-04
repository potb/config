{inputs, ...}: final: prev: let
  pkgs-master = import inputs.nixpkgs-master {
    system = prev.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
in {
  opencode = inputs.opencode-src.packages.${prev.stdenv.hostPlatform.system}.opencode;
  jetbrains = pkgs-master.jetbrains;
}

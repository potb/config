{inputs, ...}: final: prev: let
  pkgs-master = import inputs.nixpkgs-master {
    system = prev.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
in {
  opencode = pkgs-master.opencode;
  jetbrains = pkgs-master.jetbrains;
}

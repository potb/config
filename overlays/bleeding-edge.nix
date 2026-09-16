{inputs, ...}: final: prev: let
  pkgs-master = import inputs.nixpkgs-master {
    system = prev.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
in {
  jetbrains = pkgs-master.jetbrains;
}

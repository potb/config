{inputs, ...}: final: prev: let
  pkgs-master = import inputs.nixpkgs-master {
    system = prev.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
in {
  opencode = let
    upstream = inputs.opencode-src.packages.${prev.stdenv.hostPlatform.system}.opencode;
    # Upstream's hashes.json lags its own production branch, so each system
    # needs the hash its lockfile actually produces. A system missing here
    # falls back to upstream and fails the fixed-output check with the value
    # to record.
    nodeModulesHashes = {
      x86_64-linux = "sha256-Uizt9NXuovBdQg0ff+x4VFn5pRvB4RUV+4LwY4Cfrvk=";
      aarch64-darwin = "sha256-b+h+QYcJ3OunhlLcd+1ni/XOcfwwI1S+douLJ/4blYs=";
    };
    system = prev.stdenv.hostPlatform.system;
  in
    if nodeModulesHashes ? ${system}
    then
      upstream.override {
        node_modules = upstream.node_modules.override {
          hash = nodeModulesHashes.${system};
        };
      }
    else upstream;
  jetbrains = pkgs-master.jetbrains;
}

{inputs, ...}: final: prev: let
  pkgs-master = import inputs.nixpkgs-master {
    system = prev.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
in {
  opencode = let
    upstream = inputs.opencode-src.packages.${prev.stdenv.hostPlatform.system}.opencode;
    nodeModulesHashes = {
      x86_64-linux = "sha256-Uizt9NXuovBdQg0ff+x4VFn5pRvB4RUV+4LwY4Cfrvk=";
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

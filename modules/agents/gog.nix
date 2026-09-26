{...}: {
  nixos = {};

  darwin = {};

  home = {
    config,
    lib,
    pkgs,
    ...
  }: let
    accountFile = config.sops.secrets.gog-account.path;

    gog = pkgs.writeShellScriptBin "gog" ''
      if [ -z "''${GOG_ACCOUNT:-}" ] && [ -r ${lib.escapeShellArg accountFile} ]; then
        GOG_ACCOUNT=$(cat ${lib.escapeShellArg accountFile})
        export GOG_ACCOUNT
      fi
      exec ${lib.getExe' pkgs.gogcli "gog"} "$@"
    '';
  in {
    home.packages = [gog];

    sops.secrets.gog-account = {};
  };
}

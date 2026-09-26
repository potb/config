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
    passwordFile = config.sops.secrets.gog-keyring-password.path;

    gog = pkgs.writeShellScriptBin "gog" ''
      if [ -z "''${GOG_ACCOUNT:-}" ] && [ -r ${lib.escapeShellArg accountFile} ]; then
        GOG_ACCOUNT=$(cat ${lib.escapeShellArg accountFile})
        export GOG_ACCOUNT
      fi
      if [ -z "''${GOG_KEYRING_PASSWORD:-}" ] && [ -r ${lib.escapeShellArg passwordFile} ]; then
        GOG_KEYRING_PASSWORD=$(cat ${lib.escapeShellArg passwordFile})
        export GOG_KEYRING_PASSWORD
      fi
      export GOG_KEYRING_BACKEND=file
      exec ${lib.getExe' pkgs.gogcli "gog"} "$@"
    '';
  in {
    home.packages = [gog];

    sops.secrets = {
      gog-account = {};
      gog-keyring-password = {};
    };
  };
}

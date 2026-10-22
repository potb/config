{
  config,
  pkgs,
  lib,
  ...
}: let
  python = pkgs.python3.withPackages (p: [p.tzdata]);
  motisState = "/var/lib/motis";

  transit =
    pkgs.runCommand "transit" {
      meta.mainProgram = "transit";
    } ''
      install -Dm644 ${./transit.py} $out/lib/transit/transit.py
      install -Dm644 ${./transit_prim.py} $out/lib/transit/transit_prim.py
      mkdir -p $out/bin
      printf '#!%s\nexec %s %s "$@"\n' \
        ${pkgs.runtimeShell} ${lib.getExe python} $out/lib/transit/transit.py > $out/bin/transit
      chmod +x $out/bin/transit
    '';
in {
  nixos = {
    services.openclaw-gateway.servicePath = [transit];

    systemd.services.openclaw-gateway = {
      environment = {
        TRANSIT_LOCAL_URL = "http://127.0.0.1:8090";
        TRANSIT_USER_AGENT = "potb-transit/1.0 (+https://github.com/potb/config)";
        TRANSIT_MOTIS_STATE = motisState;
        PRIM_API_KEY_FILE = config.sops.secrets.transit-prim-api-key.path;
      };
      serviceConfig.ReadWritePaths = ["-${motisState}/requests"];
    };

    users.users.openclaw.extraGroups = ["motis"];
    users.groups.motis = {};

    environment.systemPackages = [transit];
  };

  darwin = {};
  home = {};
}

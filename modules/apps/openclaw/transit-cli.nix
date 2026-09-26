{
  pkgs,
  lib,
  ...
}: let
  python = pkgs.python3.withPackages (p: [p.tzdata]);
  motisState = "/var/lib/motis";

  transit = pkgs.writeScriptBin "transit" (
    "#!${lib.getExe python}\n" + builtins.readFile ./transit.py
  );
in {
  nixos = {
    services.openclaw-gateway.servicePath = [transit];

    systemd.services.openclaw-gateway = {
      environment = {
        TRANSIT_LOCAL_URL = "http://127.0.0.1:8090";
        TRANSIT_USER_AGENT = "potb-transit/1.0 (+https://github.com/potb/config)";
        TRANSIT_MOTIS_STATE = motisState;
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

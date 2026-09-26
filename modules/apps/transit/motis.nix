{
  config,
  pkgs,
  lib,
  ...
}: let
  port = 8090;
  stateDir = "/var/lib/motis";
  userAgent = "potb-transit/1.0 (+https://github.com/potb/config)";

  hasPinnedSecret = config ? sops && config.sops.secrets ? transit-pinned-regions;
  pinnedRegionsFile =
    if hasPinnedSecret
    then config.sops.secrets.transit-pinned-regions.path
    else "/dev/null";

  regionsConfig = {
    inherit stateDir userAgent;

    pinnedFile = pinnedRegionsFile;
    maxRegions = 3;
    requestTtlDays = 14;
    rebuildAfterDays = 3;

    nationalFeeds = ["horaires-sncf"];

    mirror = "https://api.transitous.org/gtfs";
    catalogUrls = {
      geofabrik = "https://download.geofabrik.de/index-v1.json";
      transitous = "https://raw.githubusercontent.com/public-transport/transitous/main/feeds/fr.json";
      pan = "https://transport.data.gouv.fr/api/datasets";
      epcis = "https://geo.api.gouv.fr/epcis?fields=code,codesDepartements";
      departements = "https://geo.api.gouv.fr/departements?fields=code,codeRegion";
    };

    motisConfig = {
      user_agent = userAgent;
      server = {
        host = "127.0.0.1";
        port = toString port;
        web_folder = "${pkgs.motis}/share/motis/ui";
      };
      street_routing = true;
      osr_footpath = false;
      elevators = false;
      geocoding = true;
      reverse_geocoding = true;
      timetable = {
        first_day = "TODAY";
        num_days = 60;
        railviz = true;
        with_shapes = true;
        adjust_footpaths = true;
        merge_dupes_intra_src = true;
        merge_dupes_inter_src = true;
        link_stop_distance = 100;
        update_interval = 60;
        http_timeout = 30;
        incremental_rt_update = false;
        preprocess_max_matching_distance = 0;
        max_footpath_length = 12;
        extend_missing_footpaths = true;
      };
    };
  };

  regionsConfigFile = pkgs.writeText "motis-regions.json" (builtins.toJSON regionsConfig);

  motisRegions = pkgs.writeShellApplication {
    name = "motis-regions";
    runtimeInputs = [pkgs.motis pkgs.osmium-tool];
    text = ''
      export MOTIS_REGIONS_CONFIG="''${MOTIS_REGIONS_CONFIG:-${regionsConfigFile}}"
      exec ${lib.getExe pkgs.python3} ${./regions.py} "$@"
    '';
  };

  serveNewImport = pkgs.writeShellScript "motis-serve-new-import" ''
    if [ -e ${stateDir}/switched ]; then
      rm -f ${stateDir}/switched
      ${pkgs.systemd}/bin/systemctl restart motis.service
    else
      ${pkgs.systemd}/bin/systemctl start --no-block motis.service
    fi
  '';

  hardening = {
    NoNewPrivileges = true;
    ProtectSystem = "strict";
    ProtectHome = true;
    PrivateTmp = true;
    PrivateDevices = true;
    ProtectKernelTunables = true;
    ProtectKernelModules = true;
    ProtectKernelLogs = true;
    ProtectControlGroups = true;
    ProtectClock = true;
    ProtectHostname = true;
    RestrictAddressFamilies = ["AF_INET" "AF_INET6" "AF_UNIX"];
    RestrictNamespaces = true;
    RestrictRealtime = true;
    RestrictSUIDSGID = false;
    LockPersonality = true;
    SystemCallArchitectures = "native";
    CapabilityBoundingSet = "";
  };
in {
  nixos = {
    users.users.motis = {
      isSystemUser = true;
      group = "motis";
      home = stateDir;
    };
    users.groups.motis = {};

    systemd.tmpfiles.rules = [
      "d ${stateDir} 0755 motis motis - -"
      "d ${stateDir}/requests 2770 motis motis - -"
      "d ${stateDir}/catalog 0755 motis motis - -"
    ];

    systemd.services.motis = {
      description = "MOTIS public transport router, loopback on ${toString port}";
      wantedBy = ["multi-user.target"];
      after = ["network-online.target"];
      wants = ["network-online.target"];

      unitConfig.ConditionPathExists = "${stateDir}/current/data";

      serviceConfig =
        hardening
        // {
          User = "motis";
          Group = "motis";
          WorkingDirectory = "${stateDir}/current";
          ExecStart = "${lib.getExe pkgs.motis} server -d data --log-level info";
          Restart = "on-failure";
          RestartSec = 10;
          ReadOnlyPaths = [stateDir];
          MemoryHigh = "1792M";
          MemoryMax = "2G";
        };
    };

    systemd.services.motis-import = {
      description = "Rebuild the MOTIS import for the regions in use";
      after = ["network-online.target"] ++ lib.optional hasPinnedSecret "sops-nix.service";
      wants = ["network-online.target"] ++ lib.optional hasPinnedSecret "sops-nix.service";

      serviceConfig =
        hardening
        // {
          Type = "oneshot";
          User = "motis";
          Group = "motis";
          StateDirectory = "motis";
          ExecStart = "${lib.getExe motisRegions} sync";
          ExecStopPost = "+${serveNewImport}";
          Nice = 10;
          IOSchedulingClass = "idle";
          CPUQuota = "300%";
          MemoryHigh = "3G";
          MemoryMax = "4G";
          TimeoutStartSec = "2h";
        };
    };

    systemd.paths.motis-import = {
      description = "Rebuild MOTIS when a region is requested";
      wantedBy = ["paths.target"];
      pathConfig.PathChanged = "${stateDir}/requests";
    };

    systemd.timers.motis-import = {
      wantedBy = ["timers.target"];
      timerConfig = {
        OnCalendar = "*-*-* 04:30:00";
        OnBootSec = "5min";
        RandomizedDelaySec = "30min";
        Persistent = true;
      };
    };

    environment.systemPackages = [pkgs.motis motisRegions];
  };

  darwin = {};
  home = {};
}

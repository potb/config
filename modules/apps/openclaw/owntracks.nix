{
  config,
  pkgs,
  lib,
  ...
}: let
  port = 8765;
  dataDir = "/var/lib/owntracks";
  retentionDays = 30;

  python = pkgs.python3.withPackages (p: [p.tzdata]);

  receiver = pkgs.writeScript "owntracks-receiver" (
    "#!${lib.getExe pkgs.python3}\n" + builtins.readFile ./owntracks-receiver.py
  );

  loc = pkgs.writeScriptBin "loc" (
    "#!${lib.getExe python}\n" + builtins.readFile ./loc.py
  );

  prune = pkgs.writeShellScript "owntracks-prune" ''
    set -eu
    cutoff=$(( $(${pkgs.coreutils}/bin/date +%s) - ${toString retentionDays} * 86400 ))
    for f in ${dataDir}/history.jsonl ${dataDir}/transitions.jsonl; do
      [ -f "$f" ] || continue
      ${pkgs.jq}/bin/jq -c --argjson cutoff "$cutoff" 'select(.ts >= $cutoff)' "$f" > "$f.new"
      ${pkgs.coreutils}/bin/chmod 0640 "$f.new"
      ${pkgs.coreutils}/bin/mv "$f.new" "$f"
    done
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
    LockPersonality = true;
    SystemCallArchitectures = "native";
    CapabilityBoundingSet = "";
    IPAddressAllow = "localhost";
    IPAddressDeny = "any";
  };
in {
  nixos = {
    users.users.owntracks = {
      isSystemUser = true;
      group = "owntracks";
      home = dataDir;
    };
    users.groups.owntracks = {};
    users.users.openclaw.extraGroups = ["owntracks"];

    systemd.services.owntracks-receiver = {
      description = "Receive the phone's position from OwnTracks, loopback on ${toString port}";
      wantedBy = ["multi-user.target"];
      after = ["network.target" "sops-nix.service"];
      wants = ["sops-nix.service"];

      environment = {
        LOC_DATA_DIR = dataDir;
        LOC_HOST = "127.0.0.1";
        LOC_PORT = toString port;
        LOC_USER = "owntracks";
        LOC_PASSWORD_FILE = config.sops.secrets.owntracks-password.path;
        LOC_ALLOWED_LOGINS = "peio.thibault@gmail.com";
      };

      serviceConfig =
        hardening
        // {
          User = "owntracks";
          Group = "owntracks";
          StateDirectory = "owntracks";
          StateDirectoryMode = "0750";
          UMask = "0027";
          ExecStart = receiver;
          Restart = "on-failure";
          RestartSec = 5;
          MemoryMax = "128M";
        };
    };

    systemd.services.owntracks-prune = {
      description = "Drop phone positions older than ${toString retentionDays} days";
      serviceConfig =
        hardening
        // {
          Type = "oneshot";
          User = "owntracks";
          Group = "owntracks";
          ReadWritePaths = [dataDir];
          ExecStart = prune;
        };
    };

    systemd.timers.owntracks-prune = {
      wantedBy = ["timers.target"];
      timerConfig = {
        OnCalendar = "daily";
        Persistent = true;
      };
    };

    services.openclaw-gateway.servicePath = [loc];
    systemd.services.openclaw-gateway.environment.LOC_DATA_DIR = dataDir;

    environment.systemPackages = [loc];
  };

  darwin = {};
  home = {};
}

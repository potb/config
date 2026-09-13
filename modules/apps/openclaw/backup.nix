{config, ...}: {
  nixos = {
    services.restic.backups.openclaw = {
      initialize = true;
      repository = "/var/lib/backup/restic";
      passwordFile = config.sops.secrets.restic-password.path;

      paths = [
        "/var/lib/openclaw"
        "/var/lib/neko/profile"
      ];

      exclude = [
        "/var/lib/openclaw/logs"
        "/var/lib/openclaw/**/node_modules"
        "/var/lib/neko/profile/*/Cache"
        "/var/lib/neko/profile/*/Code Cache"
        "/var/lib/neko/profile/*/GPUCache"
      ];

      timerConfig = {
        OnCalendar = "03:30";
        RandomizedDelaySec = "30m";
        Persistent = true;
      };

      pruneOpts = [
        "--keep-daily 7"
        "--keep-weekly 5"
        "--keep-monthly 6"
      ];
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/backup 0700 root root - -"
    ];
  };

  darwin = {};
  home = {};
}

{
  config,
  pkgs,
  ...
}: let
  nekoImage = "ghcr.io/m1k1o/neko/chromium:3.1.5";

  cdpPort = 9223;

  supervisordChromium = pkgs.writeText "neko-chromium.conf" ''
    [program:chromium]
    environment=HOME="/home/%(ENV_USER)s",USER="%(ENV_USER)s",DISPLAY="%(ENV_DISPLAY)s"
    command=/usr/bin/chromium
      --no-sandbox
      --window-position=0,0
      --display=%(ENV_DISPLAY)s
      --user-data-dir=/home/neko/.config/chromium
      --no-first-run
      --start-maximized
      --force-dark-mode
      --disable-gpu
      --disable-software-rasterizer
      --disable-dev-shm-usage
      --remote-debugging-port=${toString cdpPort}
      --remote-debugging-address=0.0.0.0
      --remote-allow-origins=*
    stopsignal=INT
    autorestart=true
    priority=800
    user=%(ENV_USER)s
    stdout_logfile=/var/log/neko/chromium.log
    stdout_logfile_maxbytes=100MB
    stdout_logfile_backups=10
    redirect_stderr=true
  '';
in {
  nixos = {
    virtualisation.podman = {
      enable = true;
      dockerCompat = false;
      defaultNetwork.settings.dns_enabled = true;
    };

    virtualisation.oci-containers = {
      backend = "podman";

      containers.neko = {
        image = nekoImage;
        autoStart = true;

        environment = {
          NEKO_DESKTOP_SCREEN = "1920x1080@30";
          NEKO_MEMBER_PROVIDER = "multiuser";
          NEKO_WEBRTC_NAT1TO1 = "127.0.0.1";
          NEKO_WEBRTC_EPR = "52000-52100";
          NEKO_WEBRTC_ICELITE = "true";
        };

        environmentFiles = [config.sops.secrets.neko-env.path];

        ports = [
          "127.0.0.1:8080:8080"
          "127.0.0.1:${toString cdpPort}:${toString cdpPort}"
          "127.0.0.1:52000-52100:52000-52100/udp"
        ];

        volumes = [
          "/var/lib/neko/profile:/home/neko/.config/chromium"
          "/var/lib/neko/downloads:/home/neko/Downloads"
          "${supervisordChromium}:/etc/neko/supervisord/chromium.conf:ro"
        ];

        extraOptions = [
          "--shm-size=2g"
          "--cap-add=SYS_ADMIN"
          "--memory=3g"
          "--memory-swap=3g"
        ];
      };
    };

    systemd.services.podman-neko = {
      after = ["network-online.target"];
      wants = ["network-online.target"];
      serviceConfig = {
        Restart = "on-failure";
        RestartSec = 30;
      };
      unitConfig = {
        StartLimitIntervalSec = 600;
        StartLimitBurst = 10;
      };
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/neko 0750 root root - -"
      "d /var/lib/neko/profile 0777 root root - -"
      "d /var/lib/neko/downloads 0777 root root - -"
    ];

    environment.systemPackages = [pkgs.podman-tui];
  };

  darwin = {};
  home = {};
}

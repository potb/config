{
  config,
  pkgs,
  ...
}: let
  nekoImage = "ghcr.io/m1k1o/neko/chromium:3.1.0";

  chromeFlags = builtins.concatStringsSep " " [
    "--remote-debugging-port=9223"
    "--remote-debugging-address=0.0.0.0"
    "--remote-allow-origins=*"
    "--no-first-run"
    "--disable-features=Translate"
  ];
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
          NEKO_CHROME_FLAGS = chromeFlags;
        };

        environmentFiles = [config.sops.secrets.neko-env.path];

        ports = [
          "127.0.0.1:8080:8080"
          "127.0.0.1:9223:9223"
          "127.0.0.1:52000-52100:52000-52100/udp"
        ];

        volumes = [
          "/var/lib/neko/profile:/home/neko/.config/chromium"
          "/var/lib/neko/downloads:/home/neko/Downloads"
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

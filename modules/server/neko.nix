{
  config,
  pkgs,
  ...
}: let
  nekoImage = "ghcr.io/m1k1o/neko/chromium:3.1.5";

  cdpPort = 9223;
  bridgePort = 9222;

  mediaPort = 52100;

  nekoAddressEnv = "/run/neko/address.env";

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
          NEKO_WEBRTC_TCPMUX = toString mediaPort;
          NEKO_WEBRTC_ICELITE = "true";
        };

        environmentFiles = [
          config.sops.secrets.neko-env.path
          nekoAddressEnv
        ];

        ports = [
          "127.0.0.1:8080:8080"
          "127.0.0.1:${toString bridgePort}:${toString bridgePort}"
          "127.0.0.1:${toString mediaPort}:${toString mediaPort}"
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

    systemd.services.neko-address = {
      description = "Resolve the tailnet address Neko advertises to WebRTC clients";
      wantedBy = ["multi-user.target"];
      before = ["podman-neko.service"];
      requiredBy = ["podman-neko.service"];
      after = ["tailscaled.service"];
      wants = ["tailscaled.service"];

      path = with pkgs; [tailscale coreutils];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };

      script = ''
        mkdir -p "$(dirname ${nekoAddressEnv})"

        address=""
        attempt=0
        while [ "$attempt" -lt 60 ]; do
          address=$(tailscale ip -4 2>/dev/null || true)
          if [ -n "$address" ]; then
            break
          fi
          attempt=$((attempt + 1))
          sleep 2
        done

        if [ -z "$address" ]; then
          echo "no tailnet address available" >&2
          exit 1
        fi

        printf 'NEKO_WEBRTC_NAT1TO1=%s\n' "$address" > ${nekoAddressEnv}
      '';
    };

    systemd.services.neko-cdp-bridge = {
      description = "Forward the Neko CDP port off the container's loopback";
      wantedBy = ["multi-user.target"];
      after = ["podman-neko.service"];
      bindsTo = ["podman-neko.service"];

      path = with pkgs; [podman socat];

      script = ''
        netns=$(podman inspect neko --format '{{.NetworkSettings.SandboxKey}}')
        exec ${pkgs.iproute2}/bin/ip netns exec "$(basename "$netns")" \
          socat TCP-LISTEN:${toString bridgePort},fork,reuseaddr \
          TCP:127.0.0.1:${toString cdpPort}
      '';

      serviceConfig = {
        Restart = "always";
        RestartSec = 10;
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

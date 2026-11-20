{
  config,
  inputs,
  lib,
  pkgs,
  ...
}: let
  instances = lib.range 1 6;
  dockerIndex = 7;
  lightInstances = [8 9];
  lightLabels = "\${RUNNER_DOCKER_LABELS%-docker}-light";
  runnerUnits = map (index: "ci-runner-${toString index}.service") (instances ++ [dockerIndex] ++ lightInstances);

  settingsCredential = "env:${config.sops.secrets.ci-runner-env.path}";
  credentials = [
    settingsCredential
    "app-key:${config.sops.secrets.ci-runner-app-key.path}"
  ];

  loadSettings = ''
    set -a
    . "$CREDENTIALS_DIRECTORY/env"
    set +a
  '';

  appToken = pkgs.writeShellApplication {
    name = "ci-runner-app-token";
    runtimeInputs = with pkgs; [curl jq openssl coreutils];
    text = ''
      key="$1"
      b64() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }
      now=$(date +%s)
      header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64)
      payload=$(printf '{"iat":%d,"exp":%d,"iss":%s}' "$((now - 60))" "$((now + 540))" "$RUNNER_APP_ID" | b64)
      signature=$(printf '%s.%s' "$header" "$payload" | openssl dgst -sha256 -sign "$key" -binary | b64)
      jwt="$header.$payload.$signature"
      api() { curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" -H "Authorization: Bearer $jwt" "$@"; }
      installation=$(api "https://api.github.com/repos/$RUNNER_REPO/installation" | jq -r .id)
      api -X POST "https://api.github.com/app/installations/$installation/access_tokens" | jq -r .token
    '';
  };

  github = pkgs.writeShellApplication {
    name = "ci-runner-github";
    runtimeInputs = with pkgs; [curl];
    text = ''
      token=$(${lib.getExe appToken} "''${APP_KEY_FILE:-$CREDENTIALS_DIRECTORY/app-key}")
      curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" -H "Authorization: token $token" "$@"
    '';
  };

  registrationToken = pkgs.writeShellApplication {
    name = "ci-runner-registration-token";
    runtimeInputs = with pkgs; [coreutils jq];
    excludeShellChecks = ["SC1091"];
    text = ''
      if [ -n "''${1:-}" ]; then
        ${lib.getExe waitForRoom} "$1"
      fi
      set -a
      . ${config.sops.secrets.ci-runner-env.path}
      set +a
      export APP_KEY_FILE=${config.sops.secrets.ci-runner-app-key.path}
      target="$RUNTIME_DIRECTORY/registration-token"
      ${lib.getExe github} -X POST "https://api.github.com/repos/$RUNNER_REPO/actions/runners/registration-token" | jq -r .token > "$target"
      chown --reference="$RUNTIME_DIRECTORY" "$target"
      chmod 0400 "$target"
    '';
  };

  waitForRoom = pkgs.writeShellApplication {
    name = "ci-runner-wait-for-room";
    runtimeInputs = with pkgs; [coreutils gawk];
    text = ''
      limit="$1"
      while true; do
        pressure=$(awk '/^some/ { split($3, a, "="); print int(a[2]) }' /proc/pressure/cpu)
        available=$(awk '/^MemAvailable/ { print int($2 / 1048576) }' /proc/meminfo)
        if [ "$pressure" -lt "$limit" ] && [ "$available" -ge 16 ]; then
          exit 0
        fi
        echo "waiting for room: cpu pressure ''${pressure}% over 60 s (limit ''${limit}%), ''${available} GiB available"
        sleep 30
      done
    '';
  };

  pressureLimit = index:
    if index <= 1 || builtins.elem index lightInstances
    then null
    else if index <= 3
    then 60
    else if index <= 5
    then 40
    else 25;

  dockerData = "/var/lib/ci-docker";

  configureRunner = index: labels: ''
    token=$(cat /tmp/registration-token)
    rm -f /tmp/registration-token
    ${pkgs.github-runner}/bin/config.sh --unattended --ephemeral --replace --disableupdate \
      --url "https://github.com/$RUNNER_REPO" --token "$token" \
      --name "$(${pkgs.hostname}/bin/hostname)-${toString index}" --labels "${labels}" \
      --work /tmp/work
  '';

  insideDocker = pkgs.writeShellScript "ci-runner-inside-docker" ''
    rm -rf /run/docker.sock /run/docker /run/containerd /run/docker.pid
    export DOCKER_HOST=unix:///tmp/docker/docker.sock
    mkdir -p /tmp/docker
    dockerd --data-root ${dockerData}/data --exec-root /tmp/docker/exec --pidfile /tmp/docker/docker.pid \
      --host "$DOCKER_HOST" --exec-opt native.cgroupdriver=cgroupfs --cgroup-parent "$CI_CGROUP/docker" --bip 10.201.0.1/16 --default-address-pool base=10.202.0.0/16,size=24 \
      > /tmp/dockerd.log 2>&1 &
    dockerd_pid=$!
    ln -sf /tmp/docker/docker.sock /run/docker.sock
    for _ in $(seq 1 60); do docker info > /dev/null 2>&1 && break; sleep 1; done
    docker info > /dev/null || { cat /tmp/dockerd.log; exit 1; }
    docker ps -aq | xargs -r docker rm -f
    docker volume ls -q | xargs -r docker volume rm -f
    docker network prune -f
    export RUNNER_ALLOW_RUNASROOT=1
    ${configureRunner dockerIndex "$RUNNER_DOCKER_LABELS"}
    ${pkgs.github-runner}/bin/run.sh
    kill "$dockerd_pid"
  '';

  takeToken = ''
    mv "$RUNTIME_DIRECTORY/registration-token" /tmp/registration-token
  '';

  basePath = with pkgs; [
    bash
    coreutils
    git
    gnutar
    gzip
    xz
    zstd
    unzip
    gnused
    gawk
    findutils
    which
    procps
    curl
    jq
    gh
    python3
    nodejs_24
    postgresql_17
  ];

  dockerPath = with pkgs; [docker containerd runc rootlesskit slirp4netns iptables iproute2 util-linux kmod];

  environment = {
    NIX_LD = config.environment.variables.NIX_LD;
    NIX_LD_LIBRARY_PATH = lib.concatStringsSep ":" [
      config.environment.variables.NIX_LD_LIBRARY_PATH
      (lib.makeLibraryPath (with pkgs; [
        glib
        nss
        nspr
        atk
        at-spi2-atk
        at-spi2-core
        cups
        dbus
        libdrm
        expat
        libxkbcommon
        libgbm
        mesa
        pango
        harfbuzz
        cairo
        alsa-lib
        fontconfig
        freetype
        udev
        libx11
        libxcomposite
        libxdamage
        libxext
        libxfixes
        libxrandr
        libxcb
        libxshmfence
      ]))
    ];
    FONTCONFIG_FILE = "${pkgs.fontconfig.out}/etc/fonts/fonts.conf";
    CIRCLE_NODE_TOTAL = "4";
  };

  sandbox = {
    LoadCredential = [settingsCredential];
    ExecStartPre = "+${lib.getExe registrationToken}";
    TimeoutStartSec = "infinity";
    Restart = "always";
    RestartSec = 5;
    TimeoutStopSec = 30;
    Slice = "ci-runners.slice";
    IPAddressAllow = ["localhost" "100.100.100.100"];
    IPAddressDeny = [
      "10.0.0.0/8"
      "172.16.0.0/12"
      "192.168.0.0/16"
      "100.64.0.0/10"
      "169.254.0.0/16"
      "::/0"
    ];
    Nice = 10;
    IOSchedulingClass = "idle";
    OOMScoreAdjust = 1000;
    ProtectHome = true;
    ProtectSystem = "strict";
    PrivateTmp = true;
    ProtectKernelModules = true;
  };

  runner = index: let
    light = builtins.elem index lightInstances;
  in {
    name = "ci-runner-${toString index}";
    value = {
      description = "Ephemeral CI runner ${toString index}${lib.optionalString light " for short jobs"}";
      wantedBy = ["multi-user.target"];
      restartIfChanged = false;
      after = ["network-online.target"];
      wants = ["network-online.target"];
      path = basePath;
      inherit environment;
      script = ''
        ${loadSettings}
        export HOME=/tmp/home RUNNER_ROOT=/tmp/runner
        mkdir -p "$HOME" "$RUNNER_ROOT"
        ${takeToken}
        ${configureRunner index (
          if light
          then lightLabels
          else "$RUNNER_LABELS"
        )}
        exec ${pkgs.github-runner}/bin/run.sh
      '';
      serviceConfig =
        sandbox
        // {
          DynamicUser = true;
          RuntimeDirectory = "ci-runner-${toString index}";
          RuntimeDirectoryMode = "0700";
          CPUAffinity =
            if light
            then "4-7"
            else "${toString (4 + index * 4)}-${toString (7 + index * 4)}";
          MemoryMax =
            if light
            then "3G"
            else "12G";
          Slice =
            if light
            then "ci.slice"
            else "ci-runners.slice";
          PrivateDevices = true;
          NoNewPrivileges = true;
          ProtectKernelTunables = true;
          ProtectControlGroups = true;
          RestrictSUIDSGID = true;
        }
        // lib.optionalAttrs (pressureLimit index != null) {
          ExecStartPre = "+${lib.getExe registrationToken} ${toString (pressureLimit index)}";
        };
    };
  };

  dockerRunner = {
    description = "Ephemeral CI runner ${toString dockerIndex} with rootless Docker";
    wantedBy = ["multi-user.target"];
    restartIfChanged = false;
    after = ["network-online.target"];
    wants = ["network-online.target"];
    path = basePath ++ dockerPath;
    inherit environment;
    script = ''
      ${loadSettings}
      export PATH=/run/wrappers/bin:$PATH HOME=/tmp/home RUNNER_ROOT=/tmp/runner XDG_RUNTIME_DIR=/tmp/xdg
      mkdir -p "$HOME" "$RUNNER_ROOT" "$XDG_RUNTIME_DIR"
      ${takeToken}
      CI_CGROUP=$(sed -n 's/^0:://p' /proc/self/cgroup)
      export CI_CGROUP
      mkdir -p "/sys/fs/cgroup$CI_CGROUP/init"
      echo $$ > "/sys/fs/cgroup$CI_CGROUP/init/cgroup.procs"
      for controller in cpu cpuset io memory pids; do
        echo "+$controller" > "/sys/fs/cgroup$CI_CGROUP/cgroup.subtree_control" || true
      done
      exec rootlesskit --net=slirp4netns --mtu=65520 --disable-host-loopback \
        --copy-up=/etc --copy-up=/run --propagation=rslave --state-dir=/tmp/rootlesskit \
        ${insideDocker}
    '';
    serviceConfig =
      sandbox
      // {
        User = "ci-docker";
        Group = "ci-docker";
        RuntimeDirectory = "ci-runner-${toString dockerIndex}";
        RuntimeDirectoryMode = "0700";
        ReadWritePaths = [dockerData];
        IPAddressAllow = sandbox.IPAddressAllow ++ ["10.0.0.0/8"];
        CPUAffinity = "4-7";
        MemoryMax = "16G";
        Delegate = true;
      };
  };

  routeFlag = value: ''
    ${loadSettings}
    ${lib.getExe github} -X PATCH "https://api.github.com/repos/$RUNNER_REPO/actions/variables/RUNNER_ROUTE_OFF" \
      -d '{"name":"RUNNER_ROUTE_OFF","value":"${value}"}'
  '';
in {
  imports = [inputs.sops-nix.nixosModules.sops];

  sops = {
    age.keyFile = "/home/potb/.config/sops/age/keys.txt";
    secrets = {
      ci-runner-env.sopsFile = ../../../secrets/ci-runner.yaml;
      ci-runner-app-key.sopsFile = ../../../secrets/ci-runner.yaml;
    };
  };

  users.groups.ci-docker = {};
  users.users.ci-docker = {
    isSystemUser = true;
    group = "ci-docker";
    home = dockerData;
    subUidRanges = [
      {
        startUid = 300000;
        count = 65536;
      }
    ];
    subGidRanges = [
      {
        startGid = 300000;
        count = 65536;
      }
    ];
  };

  systemd.tmpfiles.rules = ["d ${dockerData} 0700 ci-docker ci-docker -"];

  environment.variables.VITEST_MAX_WORKERS = "8";

  systemd.slices.ci = {
    description = "Background CI work, yields to the desktop";
    sliceConfig = {
      CPUWeight = 10;
      IOWeight = 10;
    };
  };

  systemd.slices.ci-runners = {
    description = "Shared budget of the CI runners";
    sliceConfig = {
      CPUWeight = 20;
      MemoryHigh = "26G";
      MemoryMax = "30G";
      MemorySwapMax = 0;
    };
  };

  systemd.slices.user.sliceConfig.MemoryLow = "20G";

  systemd.services =
    builtins.listToAttrs (map runner (instances ++ lightInstances))
    // {
      "ci-runner-${toString dockerIndex}" = dockerRunner;
      ci-runner-route = {
        description = "Send CI jobs to the local runners while they are up";
        wantedBy = ["multi-user.target"];
        after = ["network-online.target"] ++ runnerUnits;
        wants = ["network-online.target"];
        path = with pkgs; [coreutils jq];
        script = routeFlag "false";
        preStop = routeFlag "true";
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          DynamicUser = true;
          LoadCredential = credentials;
          TimeoutStopSec = 30;
        };
      };
    };
}

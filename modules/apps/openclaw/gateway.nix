{
  config,
  pkgs,
  lib,
  inputs,
  ...
}: let
  openclawPkgs = inputs.nix-openclaw.packages.${pkgs.stdenv.hostPlatform.system};

  runtimePlugins = [
    openclawPkgs."openclaw-runtime-plugin-exa"
    openclawPkgs."openclaw-runtime-plugin-discord"
  ];

  workspace = "/var/lib/openclaw/workspace";

  bootstrapFiles = [
    "SOUL.md"
    "AGENTS.md"
    "USER.md"
    "TOOLS.md"
  ];

  gatewayPackage = config.services.openclaw-gateway.package;

  runtimeConfigDir = "/var/lib/openclaw/config";
  runtimeConfigPath = "${runtimeConfigDir}/openclaw.json";
  agentOwnedSections = [
    "mcp"
    "skills"
  ];

  migrateStateBeforeStart = pkgs.writeShellScript "openclaw-state-migrate" ''
    set -u
    state=/var/lib/openclaw
    work=$state/doctor
    want="${gatewayPackage} $(${pkgs.coreutils}/bin/readlink -f /etc/openclaw/openclaw.json)"

    if [ "$(${pkgs.coreutils}/bin/cat "$work/stamp" 2>/dev/null)" = "$want" ]; then
      exit 0
    fi

    ${pkgs.coreutils}/bin/mkdir -p "$work"
    ${pkgs.gnutar}/bin/tar -C "$state" \
      --use-compress-program=${pkgs.gzip}/bin/gzip \
      -cf "$work/pre-migrate.tgz" state agents/main/agent || true
    ${pkgs.jq}/bin/jq 'del(.[] | select(type == "object" and has("$include")))' \
      /etc/openclaw/openclaw.json > "$work/openclaw.json"
    ${pkgs.coreutils}/bin/chmod 0600 "$work/openclaw.json"

    if OPENCLAW_NIX_MODE=0 \
      OPENCLAW_SERVICE_REPAIR_POLICY=external \
      OPENCLAW_CONFIG_PATH="$work/openclaw.json" \
      ${gatewayPackage}/bin/openclaw doctor --fix --non-interactive; then
      echo "$want" > "$work/stamp"
    else
      echo "openclaw-state-migrate: doctor --fix failed, starting the gateway anyway" >&2
    fi
    exit 0
  '';
in {
  nixos = {
    services.openclaw-gateway = {
      enable = true;
      package = openclawPkgs.openclaw;
      port = 18789;
      user = "openclaw";
      group = "openclaw";
      stateDir = "/var/lib/openclaw";

      environmentFiles = [config.sops.secrets.openclaw-env.path];

      execStartPre = ["${migrateStateBeforeStart}"];

      environment = {
        OPENCLAW_NO_RESPAWN = "1";
        NODE_COMPILE_CACHE = "/var/lib/openclaw/compile-cache";
        OPENCLAW_WORKSPACE_DIR = workspace;
        OPENCLAW_CONFIG_PATH = lib.mkForce runtimeConfigPath;
        CLAWDBOT_CONFIG_PATH = lib.mkForce runtimeConfigPath;
        OPENCLAW_NIX_MODE = "0";
        OPENCLAW_NO_AUTO_UPDATE = "1";
      };

      servicePath = with pkgs; [
        git
        ripgrep
        fd
        jq
        curl
        coreutils
        gnused
        gnugrep
        tailscale
      ];

      config = {
        gateway = {
          mode = "local";
          bind = "loopback";
          port = 18789;

          auth = {
            mode = "token";
            token = "\${OPENCLAW_GATEWAY_TOKEN}";
          };

          tailscale.mode = "off";
          trustedProxies = [
            "127.0.0.1"
            "::1"
          ];

          controlUi = {
            enabled = true;
          };
        };

        agents = {
          defaults = {
            inherit workspace;
            model = {
              primary = "openrouter/deepseek/deepseek-v4.1-flash";
              fallbacks = ["openrouter/google/gemini-3.5-flash-lite"];
            };
            userTimezone = "Europe/Paris";
            skipBootstrap = true;
            contextInjection = "continuation-skip";

            sandbox.mode = "off";
          };
        };

        env.vars = {
          OPENROUTER_API_KEY = "\${OPENROUTER_API_KEY}";
          EXA_API_KEY = "\${EXA_API_KEY}";
        };

        channels.discord = {
          enabled = true;
          token = {
            source = "env";
            provider = "default";
            id = "DISCORD_BOT_TOKEN";
          };
          applicationId = "1547996770380943360";

          dmPolicy = "allowlist";
          allowFrom = ["104696030611673088"];
          groupPolicy = "allowlist";

          guilds."1393729424398090362" = {
            requireMention = false;

            channels = {
              "1548072726571389018" = {};
              "1548072727921819699" = {};
              "1548072729000022098" = {};
            };
          };
        };

        commands.ownerAllowFrom = ["discord:104696030611673088"];

        update = {
          checkOnStart = false;
          auto.enabled = false;
        };

        mcp."$include" = "./mcp.json5";
        skills."$include" = "./skills.json5";

        session.threadBindings = {
          enabled = true;
          idleHours = 72;
          maxAgeHours = 0;
          spawnSessions = true;
          defaultSpawnContext = "fork";
        };

        tools = {
          deny = [
            "sessions_spawn"
            "sessions_send"
          ];

          fs.workspaceOnly = true;
          exec.applyPatch.workspaceOnly = true;

          web.search = {
            enabled = true;
            provider = "exa";
          };
        };

        browser = {
          enabled = true;
          defaultProfile = "neko";
          profiles.neko = {
            cdpUrl = "ws://127.0.0.1:9222";
            attachOnly = true;
          };
        };

        memory.search = {
          enabled = true;
          provider = "openrouter-embeddings";
          model = "voyageai/voyage-4-lite";
        };

        models.providers.openrouter-embeddings = {
          api = "openai-completions";
          baseUrl = "https://openrouter.ai/api/v1";
          apiKey = "\${OPENROUTER_API_KEY}";

          models = [
            {
              id = "voyageai/voyage-4-lite";
              name = "Voyage 4 Lite";
            }
          ];
        };

        plugins = {
          load.paths = map toString runtimePlugins;

          entries = {
            discord.enabled = true;
            exa.enabled = true;
          };
        };
      };
    };

    systemd.services.openclaw-gateway = {
      after = ["sops-nix.service"];
      wants = ["sops-nix.service"];
    };

    system.activationScripts.openclaw-rebind-secrets = {
      deps = ["setupSecrets"];
      text = lib.concatStringsSep "\n" ([
          "unit=openclaw-gateway.service"
          "systemctl=${config.systemd.package}/bin/systemctl"
          ""
          ''if "$systemctl" is-active --quiet "$unit"; then''
          ''pid=$("$systemctl" show -p MainPID --value "$unit")''
          "  stale=0"
        ]
        ++ map (
          name: ''${pkgs.util-linux}/bin/nsenter -t "$pid" -m -- ${pkgs.diffutils}/bin/cmp -s ${workspace}/${name} ${config.sops.secrets."workspace/${name}".path} || stale=1''
        )
        bootstrapFiles
        ++ [
          ''[ "$stale" = 0 ] || "$systemctl" restart "$unit"''
          "fi"
        ]);
    };

    systemd.services.openclaw-gateway.serviceConfig = {
      NoNewPrivileges = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectSystem = "strict";
      ProtectHome = true;
      ProtectKernelTunables = true;
      ProtectKernelModules = true;
      ProtectKernelLogs = true;
      ProtectControlGroups = true;
      ProtectClock = true;
      ProtectHostname = true;
      RestrictAddressFamilies = [
        "AF_INET"
        "AF_INET6"
        "AF_UNIX"
        "AF_NETLINK"
      ];
      RestrictNamespaces = false;
      RestrictRealtime = true;
      RestrictSUIDSGID = true;
      LockPersonality = true;
      MemoryDenyWriteExecute = false;
      SystemCallArchitectures = "native";
      CapabilityBoundingSet = "";
      AmbientCapabilities = "";
      UMask = "0077";
      TimeoutStartSec = "300";
      ReadWritePaths = [
        "/var/lib/openclaw"
      ];
      BindReadOnlyPaths =
        ["/etc/openclaw/openclaw.json:${runtimeConfigPath}"]
        ++ map (
          name: "${config.sops.secrets."workspace/${name}".path}:${workspace}/${name}"
        )
        bootstrapFiles;
      MemoryMax = "2G";
    };

    systemd.tmpfiles.rules =
      [
        "d /var/lib/openclaw/compile-cache 0750 openclaw openclaw - -"
        "d ${workspace} 0750 openclaw openclaw - -"
        "d ${workspace}/memory 0750 openclaw openclaw - -"
        "d ${runtimeConfigDir} 0700 openclaw openclaw - -"
        "f ${runtimeConfigPath} 0400 openclaw openclaw - -"
      ]
      ++ map (
        section: "f ${runtimeConfigDir}/${section}.json5 0600 openclaw openclaw - {}"
      )
      agentOwnedSections
      ++ lib.concatMap (name: [
        "r ${workspace}/${name} - - - - -"
        "f ${workspace}/${name} 0440 openclaw openclaw - -"
      ])
      bootstrapFiles;
  };

  darwin = {};
  home = {};
}

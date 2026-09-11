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

      environment = {
        OPENCLAW_NO_RESPAWN = "1";
        NODE_COMPILE_CACHE = "/var/lib/openclaw/compile-cache";
        OPENCLAW_WORKSPACE_DIR = workspace;
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
      ];

      config = {
        gateway = {
          mode = "local";
          bind = "loopback";
          port = 18789;

          auth = {
            mode = "token";
            token = "\${OPENCLAW_GATEWAY_TOKEN}";
            allowTailscale = true;
          };

          tailscale.mode = "serve";

          controlUi = {
            enabled = true;
          };
        };

        agents = {
          defaults = {
            inherit workspace;
            model = "openrouter/deepseek/deepseek-v4.1-flash";
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
          };
        };

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
            cdpUrl = "ws://127.0.0.1:9223";
            attachOnly = true;
            color = "#d84a31";
          };
        };

        memory.backend = "builtin";

        plugins.load.paths = map toString runtimePlugins;
      };
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
      TimeoutStartSec = "90";
      ReadWritePaths = [
        "/var/lib/openclaw"
      ];
      MemoryMax = "2G";
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/openclaw/compile-cache 0750 openclaw openclaw - -"
      "d ${workspace} 0750 openclaw openclaw - -"
      "d ${workspace}/memory 0750 openclaw openclaw - -"
    ];
  };

  darwin = {};
  home = {};
}

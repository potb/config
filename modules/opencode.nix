{
  pkgs,
  lib,
  inputs,
  ...
}: let
  # To add a new MCP with credentials:
  #
  # 1. Secret as command argument:
  #    mcpFooWrapper = pkgs.writeShellScript "mcp-foo" ''
  #      SECRET=$(tr -d '\n' < "$HOME/.secrets/foo-key")
  #      exec command "$SECRET"
  #    '';
  #
  # 2. Secret as environment variable:
  #    mcpBarWrapper = pkgs.writeShellScript "mcp-bar" ''
  #      export API_KEY=$(tr -d '\n' < "$HOME/.secrets/bar-api-key")
  #      exec command --arg value
  #    '';
  agentmemoryVersion =
    (builtins.fromJSON (builtins.readFile "${inputs.agentmemory}/package.json")).version;
in {
  nixos = {};
  darwin = {};
  home = {
    config,
    pkgs,
    lib,
    ...
  }: let
    opencodeConfig = {
      "$schema" = "https://opencode.ai/config.json";

      agent = {
        build = {
          model = "anthropic/claude-sonnet-5";
        };
        plan = {
          model = "anthropic/claude-opus-4-8";
        };
        title = {
          model = "anthropic/claude-haiku-4-5";
        };
        summary = {
          model = "anthropic/claude-haiku-4-5";
        };
        compaction = {
          model = "anthropic/claude-sonnet-5";
        };
        explore = {
          model = "anthropic/claude-haiku-4-5";
          permission = {
            external_directory = {
              "*" = "ask";
              "/tmp/**" = "allow";
              "${config.home.homeDirectory}/.local/share/opencode/repos/**" = "allow";
              "${config.home.homeDirectory}/.config/opencode/**" = "allow";
              "${config.home.homeDirectory}/.cache/opencode/**" = "allow";
            };
          };
        };
        general = {
          model = "anthropic/claude-sonnet-5";
        };
      };

      disabled_providers = ["zen"];
      enabled_providers = ["anthropic" "google"];
      provider = {
        anthropic = {
          whitelist = ["claude-sonnet-5" "claude-opus-4-8" "claude-haiku-4-5"];
          models = {
            claude-sonnet-5 = {
              variants = {
                low = {disabled = true;};
                high = {disabled = true;};
                max = {disabled = true;};
              };
            };
            claude-opus-4-8 = {
              variants = {
                low = {disabled = true;};
                high = {disabled = true;};
                xhigh = {disabled = true;};
                max = {disabled = true;};
              };
            };
            claude-haiku-4-5 = {
              variants = {
                max = {disabled = true;};
              };
            };
          };
        };
        google = {
          whitelist = ["gemini-3.1-pro-preview" "gemini-3.5-flash" "gemini-3.1-flash-lite"];
          models = {
            "gemini-3.5-flash" = {
              variants = {
                minimal = {disabled = true;};
                low = {disabled = true;};
                high = {disabled = true;};
              };
            };
            "gemini-3.1-pro-preview" = {
              variants = {
                low = {disabled = true;};
                high = {disabled = true;};
              };
            };
            "gemini-3.1-flash-lite" = {
              options = {
                thinkingConfig = {
                  thinkingLevel = "high";
                  includeThoughts = true;
                };
              };
            };
          };
        };
      };

      mcp = {
        agentmemory = {
          type = "local";
          command = [
            "${pkgs.fnm}/bin/fnm"
            "exec"
            "--using"
            "22"
            "npx"
            "-y"
            "@agentmemory/mcp"
          ];
          environment = {
            AGENTMEMORY_URL = "http://localhost:3111";
          };
          enabled = true;
        };
        websearch = {
          type = "remote";
          url = "https://mcp.exa.ai/mcp";
          enabled = true;
        };
        linear = {
          type = "remote";
          url = "https://mcp.linear.app/mcp";
          oauth = {};
        };
        code-docs = {
          type = "remote";
          url = "https://mcp.context7.com/mcp";
        };
        codegraph = {
          type = "local";
          command = ["codegraph" "serve" "--mcp"];
          enabled = true;
        };
      };

      plugin = let
        anthropicAuthVersion =
          (builtins.fromJSON (builtins.readFile "${inputs.opencode-anthropic-auth}/package.json")).version;
      in [
        "@ex-machina/opencode-anthropic-auth@${anthropicAuthVersion}"
        "./plugins/agentmemory-capture.ts"
        "./plugins/rtk.ts"
      ];

      references = {
        effect = {
          repository = "Effect-TS/effect";
          branch = "main";
          description = "Effect v3 source (production). Inspect for signatures, modules, API examples.";
        };
        effect-skills = {
          repository = "Effect-TS/skills";
          description = "Official Effect skills/idioms. Style authority for idiomatic Effect code.";
        };
      };

      permission = {
        external_directory = {
          "${config.home.homeDirectory}/.local/share/opencode/repos/**" = "allow";
          "${config.home.homeDirectory}/.config/opencode/**" = "allow";
          "${config.home.homeDirectory}/.cache/opencode/**" = "allow";
          "${config.home.homeDirectory}/work/**" = "allow";
        };
      };

      lsp = {
        typescript = {
          command = [
            "${config.home.homeDirectory}/.cache/opencode/packages/typescript-language-server/node_modules/.bin/typescript-language-server"
            "--stdio"
          ];
          extensions = [
            ".ts"
            ".tsx"
            ".js"
            ".jsx"
            ".mjs"
            ".cjs"
            ".mts"
            ".cts"
            ".vue"
          ];
          initialization = {
            plugins = [
              {
                name = "@vue/typescript-plugin";
                location = "${config.home.homeDirectory}/.cache/opencode/packages/@vue/language-server/node_modules/@vue/typescript-plugin";
                languages = ["vue"];
              }
            ];
          };
        };
      };

      instructions = [
        "${inputs.caveman}/src/rules/caveman-activate.md"
        "${config.home.homeDirectory}/.config/opencode/explore-usage.md"
      ];

      formatter = true;
    };
    opencodeConfigJson = builtins.toJSON opencodeConfig;
  in {
    home.activation.ensureSecretsDir = lib.hm.dag.entryAfter ["writeBoundary"] ''
      $DRY_RUN_CMD mkdir -p "$HOME/.secrets"
      $DRY_RUN_CMD chmod 700 "$HOME/.secrets"
    '';

    home.packages = [
      pkgs.codegraph
      pkgs.rtk
    ];

    systemd.user.services.agentmemory = lib.mkIf pkgs.stdenv.isLinux {
      Unit = {
        Description = "agentmemory persistent context service";
        After = ["network.target"];
      };
      Service = {
        ExecStart = "${pkgs.nodejs}/bin/npx -y @agentmemory/agentmemory@${agentmemoryVersion} serve";
        Restart = "on-failure";
        RestartSec = "5s";
        Environment = [
          "PATH=${pkgs.nodejs}/bin:/run/current-system/sw/bin:/etc/profiles/per-user/${config.home.username}/bin:${config.home.homeDirectory}/.local/bin"
        ];
      };
      Install = {
        WantedBy = ["default.target"];
      };
    };

    launchd.agents.agentmemory = lib.mkIf pkgs.stdenv.isDarwin {
      enable = true;
      config = {
        ProgramArguments = [
          "${pkgs.nodejs}/bin/npx"
          "-y"
          "@agentmemory/agentmemory@${agentmemoryVersion}"
          "serve"
        ];
        RunAtLoad = true;
        KeepAlive = {
          Crashed = true;
          SuccessfulExit = false;
        };
        StandardOutPath = "${config.home.homeDirectory}/.local/share/agentmemory/stdout.log";
        StandardErrorPath = "${config.home.homeDirectory}/.local/share/agentmemory/stderr.log";
      };
    };

    xdg.configFile = let
      caveman = inputs.caveman;
      cavemanFor = prefix: {
        "${prefix}/skills/caveman".source = "${caveman}/skills/caveman";
      };
    in
      {
        "opencode/opencode.json".text = opencodeConfigJson;
        "opencode/plugins/agentmemory-capture.ts".source = ./opencode/plugins/agentmemory-capture.ts;
        "opencode/plugins/rtk.ts".source = ./opencode/plugins/rtk.ts;
        "opencode/commands/remember.md".source = ./opencode/commands/remember.md;
        "opencode/commands/recall.md".source = ./opencode/commands/recall.md;
        "opencode/explore-usage.md".source = ./opencode/explore-usage.md;
      }
      // (cavemanFor "opencode");
  };
}

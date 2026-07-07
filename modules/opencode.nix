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
  # Secret env vars must never land in `Environment`/`EnvironmentVariables` —
  # those get baked into the world-readable nix store. Read at runtime instead,
  # same pattern as the mcpFooWrapper example above.
  agentmemoryWrapper = pkgs.writeShellScript "agentmemory-serve" ''
    if [ -f "$HOME/.secrets/gemini-api-key" ]; then
      export GEMINI_API_KEY=$(tr -d '\n' < "$HOME/.secrets/gemini-api-key")
    fi
    exec ${pkgs.nodejs}/bin/npx -y @agentmemory/agentmemory@${agentmemoryVersion} serve
  '';
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
          variant = "max";
          permission = {
            "codegraph_*" = "allow";
            "code-analytics_*" = "allow";
            "code-impact_*" = "allow";
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
          variant = "medium";
        };
      };

      disabled_providers = ["zen"];
      enabled_providers = [
        "anthropic"
        "google"
      ];
      provider = {
        anthropic = {
          whitelist = [
            "claude-sonnet-5"
            "claude-opus-4-8"
            "claude-haiku-4-5"
          ];
          models = {
            claude-sonnet-5 = {
              variants = {
                low = {
                  disabled = true;
                };
                high = {
                  disabled = true;
                };
                xhigh = {
                  disabled = true;
                };
              };
            };
            claude-opus-4-8 = {
              variants = {
                low = {
                  disabled = true;
                };
                medium = {
                  disabled = true;
                };
                high = {
                  disabled = true;
                };
                xhigh = {
                  disabled = true;
                };
              };
            };
            claude-haiku-4-5 = {};
          };
        };
        google = {
          whitelist = [
            "gemini-3.1-pro-preview"
            "gemini-3.5-flash"
            "gemini-3.1-flash-lite"
          ];
          models = {
            "gemini-3.5-flash" = {
              variants = {
                minimal = {
                  disabled = true;
                };
                low = {
                  disabled = true;
                };
                high = {
                  disabled = true;
                };
              };
            };
            "gemini-3.1-pro-preview" = {
              variants = {
                low = {
                  disabled = true;
                };
                high = {
                  disabled = true;
                };
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
          command = [
            "codegraph"
            "serve"
            "--mcp"
          ];
          enabled = true;
        };
        code-analytics = {
          type = "local";
          command = [
            "${pkgs.codebase-memory-mcp}/bin/codebase-memory-mcp"
          ];
          enabled = true;
        };
        code-impact = {
          type = "local";
          command = [
            "${pkgs.sem}/bin/sem"
            "mcp"
          ];
          enabled = true;
        };
      };

      plugin = let
        anthropicAuthVersion =
          (builtins.fromJSON (builtins.readFile "${inputs.opencode-anthropic-auth}/package.json")).version;
        dcpVersion = (builtins.fromJSON (builtins.readFile "${inputs.opencode-dcp}/package.json")).version;
      in [
        "@ex-machina/opencode-anthropic-auth@${anthropicAuthVersion}"
        "@tarquinen/opencode-dcp@${dcpVersion}"
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

      tools = {
        "code-analytics_manage_adr" = false;
        "code-analytics_detect_changes" = false;
        "code-analytics_ingest_traces" = false;
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
        "${inputs.superpowers}/skills/using-superpowers/SKILL.md"
        "${config.home.homeDirectory}/.config/opencode/explore-usage.md"
        "${config.home.homeDirectory}/.config/opencode/code-tools-priority.md"
      ];

      formatter = true;
    };
    opencodeConfigJson = builtins.toJSON opencodeConfig;

    # Absolute token caps, NOT percentages. Quality degrades well before a
    # large context window fills (NoLiMa/RULER benchmarks, Anthropic's own
    # Sonnet-4.5 1M-context mode scoring worse than its 200K mode on the same
    # tasks). A "%" limit scales the trigger point up with window size, which
    # is backwards: the quality ceiling stays roughly constant in absolute
    # tokens regardless of advertised context size. Fixed thresholds apply
    # the same whether a model claims 200K or 1M.
    dcpConfig = {
      experimental = {
        allowSubAgents = true;
      };
      compress = {
        maxContextLimit = 200000;
        minContextLimit = 150000;
        nudgeFrequency = 8;
        iterationNudgeThreshold = 20;
        nudgeForce = "soft";
      };
    };
    dcpConfigJson = builtins.toJSON dcpConfig;
  in {
    home.activation.ensureSecretsDir = lib.hm.dag.entryAfter ["writeBoundary"] ''
      $DRY_RUN_CMD mkdir -p "$HOME/.secrets"
      $DRY_RUN_CMD chmod 700 "$HOME/.secrets"
    '';

    home.packages = [
      pkgs.codegraph
      pkgs.rtk
      pkgs.codebase-memory-mcp
      pkgs.sem
    ];

    systemd.user.services.agentmemory = lib.mkIf pkgs.stdenv.isLinux {
      Unit = {
        Description = "agentmemory persistent context service";
        After = ["network.target"];
      };
      Service = {
        ExecStart = "${agentmemoryWrapper}";
        Restart = "on-failure";
        RestartSec = "5s";
        Environment = [
          "PATH=${pkgs.nodejs}/bin:/run/current-system/sw/bin:/etc/profiles/per-user/${config.home.username}/bin:${config.home.homeDirectory}/.local/bin"
          "AGENTMEMORY_SLOTS=true"
          "AGENTMEMORY_REFLECT=true"
          "GRAPH_EXTRACTION_ENABLED=true"
          "CONSOLIDATION_ENABLED=true"
          "AGENTMEMORY_AUTO_COMPRESS=true"
          "EMBEDDING_PROVIDER=local"
          "GEMINI_MODEL=gemini-3.1-flash-lite"
        ];
      };
      Install = {
        WantedBy = ["default.target"];
      };
    };

    launchd.agents.agentmemory = lib.mkIf pkgs.stdenv.isDarwin {
      enable = true;
      config = {
        ProgramArguments = ["${agentmemoryWrapper}"];
        RunAtLoad = true;
        KeepAlive = {
          Crashed = true;
          SuccessfulExit = false;
        };
        EnvironmentVariables = {
          AGENTMEMORY_SLOTS = "true";
          AGENTMEMORY_REFLECT = "true";
          GRAPH_EXTRACTION_ENABLED = "true";
          CONSOLIDATION_ENABLED = "true";
          AGENTMEMORY_AUTO_COMPRESS = "true";
          EMBEDDING_PROVIDER = "local";
          GEMINI_MODEL = "gemini-3.1-flash-lite";
        };
        StandardOutPath = "${config.home.homeDirectory}/.local/share/agentmemory/stdout.log";
        StandardErrorPath = "${config.home.homeDirectory}/.local/share/agentmemory/stderr.log";
      };
    };

    xdg.configFile = let
      mkSkill = name: src: subpath: {
        name = "opencode/skills/${name}";
        value.source =
          if subpath == null
          then src
          else "${src}/${subpath}";
      };

      # Exact subset of upstream skills we've chosen to install.
      # Anything not listed here shows up in the generated
      # opencode/skills-not-installed.md report below.
      superpowersSelected = [
        "brainstorming"
        "dispatching-parallel-agents"
        "executing-plans"
        "finishing-a-development-branch"
        "receiving-code-review"
        "requesting-code-review"
        "subagent-driven-development"
        "systematic-debugging"
        "using-git-worktrees"
        "using-superpowers"
        "verification-before-completion"
        "writing-plans"
        "writing-skills"
      ];

      mattpocockSelected = [
        "engineering/codebase-design"
        "engineering/diagnosing-bugs"
        "engineering/improve-codebase-architecture"
        "engineering/prototype"
        "engineering/tdd"
        "engineering/to-issues"
        "engineering/to-prd"
        "engineering/triage"
        "productivity/grill-me"
        "productivity/handoff"
      ];

      skillFiles = builtins.listToAttrs (
        (map (n: mkSkill (baseNameOf n) inputs.superpowers "skills/${n}") superpowersSelected)
        ++ (map (p: mkSkill (baseNameOf p) inputs.mattpocock-skills "skills/${p}") mattpocockSelected)
        ++ [
          (mkSkill "caveman" inputs.caveman "skills/caveman")
          (mkSkill "stop-slop" inputs.stop-slop null) # repo root IS the skill
        ]
      );

      # Auto-generated report of upstream skills available but not selected.
      # Regenerates from the pinned flake inputs on every rebuild/flake update.
      hasSkill = dir: builtins.pathExists "${dir}/SKILL.md";

      listFlat = src: let
        base = "${src}/skills";
        entries = builtins.readDir base;
      in
        builtins.filter (n: entries.${n} == "directory" && hasSkill "${base}/${n}") (
          builtins.attrNames entries
        );

      listNested = src: let
        base = "${src}/skills";
        categories = builtins.readDir base;
      in
        lib.concatMap (
          c:
            if categories.${c} != "directory"
            then []
            else
              map (n: "${c}/${n}") (
                builtins.filter (n: hasSkill "${base}/${c}/${n}") (
                  builtins.attrNames (builtins.readDir "${base}/${c}")
                )
              )
        ) (builtins.attrNames categories);

      spUnused = lib.subtractLists superpowersSelected (listFlat inputs.superpowers);
      mpUnused = lib.subtractLists mattpocockSelected (listNested inputs.mattpocock-skills);

      section = title: unused:
        "## ${title}\n\n"
        + (
          if unused == []
          then "- _(all upstream skills installed)_\n"
          else lib.concatMapStrings (n: "- ${n}\n") unused
        )
        + "\n";

      skillsNotInstalledReport =
        "# Upstream skills available but NOT installed\n\n"
        + "Auto-generated by Nix from pinned flake inputs. Edit selection in modules/opencode.nix.\n\n"
        + section "obra/superpowers" spUnused
        + section "mattpocock/skills" mpUnused;
    in
      {
        "opencode/opencode.json".text = opencodeConfigJson;
        "opencode/dcp.json".text = dcpConfigJson;
        "opencode/plugins/agentmemory-capture.ts".source = ./opencode/plugins/agentmemory-capture.ts;
        "opencode/plugins/rtk.ts".source = ./opencode/plugins/rtk.ts;
        "opencode/commands/remember.md".source = ./opencode/commands/remember.md;
        "opencode/commands/recall.md".source = ./opencode/commands/recall.md;
        "opencode/explore-usage.md".source = ./opencode/explore-usage.md;
        "opencode/skills-not-installed.md".text = skillsNotInstalledReport;
      }
      // skillFiles;
  };
}

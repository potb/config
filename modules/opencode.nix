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
  mcpPostgresWrapper = pkgs.writeShellScript "mcp-postgres-production" ''
    set -euo pipefail
    SECRET_FILE="$HOME/.secrets/postgres-url"
    if [ ! -f "$SECRET_FILE" ]; then
      echo "ERROR: Secret file not found: $SECRET_FILE" >&2
      echo "Create it with your postgres connection URL:" >&2
      echo "  echo 'postgresql://user:pass@host:5432/db' > $SECRET_FILE" >&2
      echo "  chmod 600 $SECRET_FILE" >&2
      exit 1
    fi
    POSTGRES_URL=$(tr -d '\n' < "$SECRET_FILE")
    exec ${pkgs.fnm}/bin/fnm exec --using 22 npx -y @modelcontextprotocol/server-postgres "$POSTGRES_URL"
  '';

  opencodeConfig = {
    "$schema" = "https://opencode.ai/config.json";
    mcp = {
      context7 = {
        type = "remote";
        url = "https://mcp.context7.com/mcp";
        enabled = true;
      };
      intercom = {
        type = "remote";
        url = "https://mcp.intercom.com/mcp";
        oauth = {};
      };
      linear = {
        type = "remote";
        url = "https://mcp.linear.app/mcp";
        oauth = {};
      };
      postgres-production = {
        type = "local";
        command = ["${mcpPostgresWrapper}"];
        enabled = true;
      };
      sentry = {
        type = "remote";
        url = "https://mcp.sentry.dev/mcp";
        oauth = {};
      };
      websearch = {
        type = "remote";
        url = "https://mcp.exa.ai/mcp?exaApiKey=__EXA_API_KEY__";
        enabled = true;
      };
      figma = {
        type = "remote";
        url = "https://mcp.figma.com/mcp";
      };
      jam = {
        type = "remote";
        url = "https://mcp.jam.dev/mcp";
      };
    };
    lsp = {
      json-ls = let
        extensions = [
          ".json"
          ".jsonc"
        ];
        schemaStoreCatalog = builtins.fromJSON (
          builtins.readFile "${inputs.schemastore}/src/api/json/catalog.json"
        );
        matchesExtension = pattern: builtins.any (ext: lib.hasSuffix ext pattern) extensions;
        schemas =
          schemaStoreCatalog.schemas
          |> builtins.filter (
            schema: schema ? fileMatch && schema ? url && builtins.any matchesExtension schema.fileMatch
          )
          |> builtins.map (schema: {
            inherit (schema) fileMatch url;
          });
      in {
        command = [
          "vscode-json-language-server"
          "--stdio"
        ];
        inherit extensions;
        initialization = {
          provideFormatter = true;
          inherit schemas;
          validate = {
            enable = true;
          };
        };
      };
    };
    plugin = let
      ohMyOpenagentVersion =
        (builtins.fromJSON (builtins.readFile "${inputs.opencode-oh-my-openagent}/package.json")).version;
      anthropicAuthVersion =
        (builtins.fromJSON (builtins.readFile "${inputs.opencode-anthropic-auth}/package.json")).version;
    in [
      "oh-my-openagent@${ohMyOpenagentVersion}"
      "@ex-machina/opencode-anthropic-auth@${anthropicAuthVersion}"
    ];
  };
  opencodeConfigJson = builtins.toJSON opencodeConfig;

  ohMyOpenagentConfig = {
    "$schema" = "https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/master/assets/oh-my-opencode.schema.json";
    agents = {
      explore = {
        model = "xai/grok-4-fast-non-reasoning";
      };
    };
    claude_code = {
      mcp = false;
      commands = false;
      skills = false;
      agents = false;
      hooks = false;
      plugins = false;
    };
    browser_automation_engine = {
      provider = "agent-browser";
    };
    git_master = {
      commit_footer = false;
      include_co_authored_by = false;
    };
    categories = {
      quick = {
        model = "xai/grok-4-1-fast-non-reasoning";
      };
    };
  };

  reviewCommandTemplate = builtins.readFile ./opencode/review-command.md;
  globalOpencodeConfig = {
    "$schema" = "https://opencode.ai/config.json";
    command = {
      review = {
        description = "4x parallel code review [commit|branch|pr], defaults to uncommitted";
        subtask = true;
        template = reviewCommandTemplate;
      };
    };
  };
in {
  nixos = {};
  darwin = {};
  home = {
    home.activation.generateOpencodeConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
            EXA_SECRET_FILE="$HOME/.secrets/exa-api-key"
            $DRY_RUN_CMD mkdir -p "$HOME/.config/opencode"

            if [ -f "$EXA_SECRET_FILE" ]; then
              OPENCODE_TEMPLATE=${pkgs.writeText "opencode.jsonc" opencodeConfigJson} \
                EXA_SECRET_FILE="$EXA_SECRET_FILE" \
                OPENCODE_OUTPUT_FILE="$HOME/.config/opencode/opencode.jsonc" \
                ${pkgs.python3}/bin/python - <<'PY'
      import os
      from pathlib import Path

      template = Path(os.environ["OPENCODE_TEMPLATE"]).read_text()
      secret = Path(os.environ["EXA_SECRET_FILE"]).read_text().replace("\n", "")
      output = Path(os.environ["OPENCODE_OUTPUT_FILE"])
      output.write_text(template.replace("__EXA_API_KEY__", secret))
      PY
              $DRY_RUN_CMD chmod 600 "$HOME/.config/opencode/opencode.jsonc"
            else
              echo "WARNING: $EXA_SECRET_FILE not found, websearch MCP will not work" >&2
              $DRY_RUN_CMD cp --remove-destination ${pkgs.writeText "opencode.jsonc" opencodeConfigJson} "$HOME/.config/opencode/opencode.jsonc"
              $DRY_RUN_CMD chmod 644 "$HOME/.config/opencode/opencode.jsonc"
            fi
    '';

    home.activation.generateOhMyOpenagentConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
      $DRY_RUN_CMD cp --remove-destination ${pkgs.writeText "oh-my-openagent.json" (builtins.toJSON ohMyOpenagentConfig)} "$HOME/.config/opencode/oh-my-openagent.json"
      $DRY_RUN_CMD chmod 644 "$HOME/.config/opencode/oh-my-openagent.json"
    '';

    home.activation.generateGlobalOpencodeConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
      $DRY_RUN_CMD mkdir -p "$HOME/.opencode"
      $DRY_RUN_CMD cp --remove-destination ${pkgs.writeText "opencode-global.json" (builtins.toJSON globalOpencodeConfig)} "$HOME/.opencode/opencode.json"
      $DRY_RUN_CMD chmod 644 "$HOME/.opencode/opencode.json"
    '';

    home.activation.ensureSecretsDir = lib.hm.dag.entryAfter ["writeBoundary"] ''
      $DRY_RUN_CMD mkdir -p "$HOME/.secrets"
      $DRY_RUN_CMD chmod 700 "$HOME/.secrets"
    '';

    xdg.configFile."opencode/command/review-loop.md".source = ./opencode/review-loop.md;
  };
}

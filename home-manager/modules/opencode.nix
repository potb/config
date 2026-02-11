{
  pkgs,
  lib,
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
    };
    plugin = [
      "oh-my-opencode@latest"
      "@franlol/opencode-md-table-formatter@latest"
    ];
  };
  opencodeConfigJson = builtins.toJSON opencodeConfig;

  ohMyOpencodeConfig = {
    "$schema" = "https://raw.githubusercontent.com/code-yeongyu/oh-my-opencode/master/assets/oh-my-opencode.schema.json";
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
    agents = {
      prometheus = {
        model = "anthropic/claude-opus-4-6";
      };
      atlas = {
        model = "anthropic/claude-sonnet-4-5";
      };
      librarian = {
        model = "anthropic/claude-haiku-4-5";
      };
      explore = {
        model = "anthropic/claude-haiku-4-5";
      };
    };
    commit_footer = false;
    commit_co_author = false;
    categories = {
      quick = {
        model = "anthropic/claude-haiku-4-5";
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
  home.activation.generateOpencodeConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
    $DRY_RUN_CMD mkdir -p "$HOME/.config/opencode"
    $DRY_RUN_CMD cp --remove-destination ${pkgs.writeText "opencode.jsonc" opencodeConfigJson} "$HOME/.config/opencode/opencode.jsonc"
    $DRY_RUN_CMD chmod 644 "$HOME/.config/opencode/opencode.jsonc"
  '';

  home.activation.generateOhMyOpencodeConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
    $DRY_RUN_CMD cp --remove-destination ${pkgs.writeText "oh-my-opencode.json" (builtins.toJSON ohMyOpencodeConfig)} "$HOME/.config/opencode/oh-my-opencode.json"
    $DRY_RUN_CMD chmod 644 "$HOME/.config/opencode/oh-my-opencode.json"
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
}

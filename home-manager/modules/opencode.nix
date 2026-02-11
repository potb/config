{
  pkgs,
  lib,
  ...
}: let
  opencodeConfig = {
    "$schema" = "https://opencode.ai/config.json";
    mcp = {
      context7 = {
        type = "remote";
        url = "https://mcp.context7.com/mcp";
        enabled = true;
      };
      linear = {
        type = "remote";
        url = "https://mcp.linear.app/mcp";
        oauth = {};
      };
      sentry = {
        type = "remote";
        url = "https://mcp.sentry.dev/mcp";
        oauth = {};
      };
      intercom = {
        type = "remote";
        url = "https://mcp.intercom.com/mcp";
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

  xdg.configFile."opencode/command/review-loop.md".source = ./opencode/review-loop.md;
}

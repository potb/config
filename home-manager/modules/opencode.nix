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
in {
  home.activation.generateOpencodeConfig = lib.hm.dag.entryAfter ["writeBoundary"] ''
    $DRY_RUN_CMD mkdir -p "$HOME/.config/opencode"
    $DRY_RUN_CMD cp --remove-destination ${pkgs.writeText "opencode.jsonc" opencodeConfigJson} "$HOME/.config/opencode/opencode.jsonc"
    $DRY_RUN_CMD chmod 644 "$HOME/.config/opencode/opencode.jsonc"
  '';
}

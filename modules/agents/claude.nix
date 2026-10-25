{
  inputs,
  lib,
  ...
}: {
  nixos = {};

  darwin = {};

  home = {
    config,
    lib,
    pkgs,
    ...
  }: let
    system = pkgs.stdenv.hostPlatform.system;
    llmAgents = inputs.llm-agents.packages.${system};
    isLinux = pkgs.stdenv.hostPlatform.isLinux;
    jq = "${pkgs.jq}/bin/jq";

    settings = {
      model = "opusplan";
      modelSettings = {
        claude-opus-5-5.effortLevel = "high";
        claude-sonnet-5-5.effortLevel = "high";
      };
      tui = "fullscreen";
      theme = "light";
      agentPushNotifEnabled = true;
      hooks.PreToolUse = [
        {
          matcher = "Edit|MultiEdit|Write|Bash";
          hooks = [
            {
              type = "command";
              command = "${pkgs.python3}/bin/python3 ${./claude/hooks/comment-guard.py}";
              timeout = 10;
            }
          ];
        }
      ];
    };

    mcpServers =
      {
        exa = {
          type = "stdio";
          command = "/bin/sh";
          args = [
            "-c"
            "exec ${pkgs.bun}/bin/bunx -y mcp-remote 'https://mcp.exa.ai/mcp?tools=web_search_exa,web_fetch_exa,web_search_advanced_exa,agent_run' --header \"x-api-key:$(cat ${config.sops.secrets.exa-api-key.path})\""
          ];
          env = {};
        };
        sentry = {
          type = "http";
          url = "https://mcp.sentry.dev/mcp";
        };
      }
      // lib.optionalAttrs isLinux {
        desktop = {
          type = "stdio";
          command = "${pkgs.computer-use-linux}/bin/computer-use-linux";
          args = ["mcp"];
          env.YDOTOOL_SOCKET = "/run/ydotoold/socket";
        };
      };

    settingsFile = pkgs.writeText "claude-settings.json" (builtins.toJSON settings);
    mcpFile = pkgs.writeText "claude-mcp.json" (builtins.toJSON mcpServers);
  in {
    home.packages =
      [llmAgents.claude-code]
      ++ lib.optional isLinux (llmAgents.claude-desktop.override {
        commandLineArgs = "--password-store=gnome-libsecret";
      });

    sops = {
      defaultSopsFile = ../../secrets/agents.yaml;
      age.sshKeyPaths = ["${config.home.homeDirectory}/.ssh/id_ed25519"];
      secrets.exa-api-key = {};
    };

    home.file.".claude/CLAUDE.md".source = ./claude/CLAUDE.md;
    home.file.".claude/skills" = {
      source = ./claude/skills;
      recursive = true;
    };

    home.activation.claudeSettings = lib.hm.dag.entryAfter ["writeBoundary"] ''
      dest="$HOME/.claude/settings.json"
      run mkdir -p "$HOME/.claude"
      if [ -f "$dest" ] && [ ! -L "$dest" ]; then
        tmp="$(mktemp)"
        ${jq} -s '.[0] * .[1]' "$dest" ${settingsFile} > "$tmp" && run install -m 0644 "$tmp" "$dest"
        rm -f "$tmp"
      else
        run rm -f "$dest"
        run install -m 0644 ${settingsFile} "$dest"
      fi
    '';

    home.activation.claudeDropJcodeHooks = lib.hm.dag.entryAfter ["claudeSettings"] ''
      dest="$HOME/.claude/settings.json"
      if [ -f "$dest" ]; then
        tmp="$(mktemp)"
        ${jq} 'if .hooks.SessionStart then .hooks.SessionStart |= map(select(all(.hooks[]?; (.command // "") | contains("jcode") | not))) else . end | if .hooks.SessionStart == [] then del(.hooks.SessionStart) else . end' "$dest" > "$tmp" && run install -m 0644 "$tmp" "$dest"
        rm -f "$tmp"
      fi
    '';

    home.activation.claudeMcp = lib.hm.dag.entryAfter ["writeBoundary"] ''
      dest="$HOME/.claude.json"
      [ -f "$dest" ] || echo '{}' > "$dest"
      tmp="$(mktemp)"
      ${jq} --slurpfile mcp ${mcpFile} '.mcpServers = $mcp[0]' "$dest" > "$tmp" && run install -m 0600 "$tmp" "$dest"
      rm -f "$tmp"
    '';
  };
}

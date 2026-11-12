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
    homeDir = config.home.homeDirectory;
    withHomeDir = name: src:
      pkgs.runCommand name {} ''
        cp -r ${src} $out
        chmod -R u+w $out
        find $out -type f -exec sed -i "s|@HOME@|${homeDir}|g" {} +
      '';
    system = pkgs.stdenv.hostPlatform.system;
    llmAgents = inputs.llm-agents.packages.${system};
    isLinux = pkgs.stdenv.hostPlatform.isLinux;
    isDarwin = pkgs.stdenv.hostPlatform.isDarwin;
    jq = "${pkgs.jq}/bin/jq";

    fableReminder = pkgs.writeShellScript "claude-fable-reminder" ''
      [ "$(${pkgs.coreutils}/bin/date +%Y%m%d)" -ge 20270309 ] && exit 0
      cat <<'EOF'
      Fable quota reminder (standing owner instruction until 2027-03-09):
      Fable 5.2 is the default model, preferred over Opus. As of 2026-11-11 the owner held 3 free Fable resets (all expire 2027-03-09) and 1 free weekly reset (expires 2026-12-10).
      Remind the owner briefly at the start of this session, and again whenever a long Fable run ends or the weekly limit nears, to check claude.ai Settings > Usage (Fable weekly bar) and to spend a Fable reset before the Fable quota runs out rather than letting it sit full. Never press the reset button yourself.
      EOF
    '';

    caffeinateSession = pkgs.writeShellScript "claude-caffeinate-session" ''
      pid=$PPID
      while [ "''${pid:-1}" -gt 1 ]; do
        [ "$(${pkgs.coreutils}/bin/basename "$(/bin/ps -o comm= -p "$pid")")" = claude ] && break
        pid=$(/bin/ps -o ppid= -p "$pid" | ${pkgs.coreutils}/bin/tr -d ' ')
      done
      [ "''${pid:-1}" -gt 1 ] || exit 0
      /usr/bin/pgrep -qf "^/usr/bin/caffeinate -i -s -w $pid$" && exit 0
      ${pkgs.coreutils}/bin/nohup /usr/bin/caffeinate -i -s -w "$pid" >/dev/null 2>&1 &
      exit 0
    '';

    settings = {
      model = "claude-fable-5-2";
      modelSettings = {
        claude-fable-5-2.effortLevel = "medium";
        claude-opus-5-5.effortLevel = "medium";
        claude-sonnet-5-5.effortLevel = "medium";
      };
      enableWorkflows = true;
      ultracode = true;
      tui = "fullscreen";
      theme = "light";
      agentPushNotifEnabled = true;
      hooks.SessionStart =
        [
          {
            hooks = [
              {
                type = "command";
                command = "${fableReminder}";
                timeout = 5;
              }
            ];
          }
        ]
        ++ lib.optional isDarwin {
          hooks = [
            {
              type = "command";
              command = "${caffeinateSession}";
              timeout = 5;
            }
          ];
        };
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
      }
      // lib.optionalAttrs isDarwin {
        desktop = {
          type = "stdio";
          command = "${pkgs.nodejs}/bin/npx";
          args = ["-y" "mac-mcp-server@0.1.3"];
        };
      };

    settingsFile = pkgs.writeText "claude-settings.json" (builtins.toJSON settings);
    mcpFile = pkgs.writeText "claude-mcp.json" (builtins.toJSON mcpServers);
  in {
    home.packages = [
      llmAgents.claude-code
      (
        if isLinux
        then
          llmAgents.claude-desktop.override {
            commandLineArgs = "--password-store=gnome-libsecret";
          }
        else llmAgents.claude-desktop
      )
    ];

    home.file.".claude/CLAUDE.md".source = ./claude/CLAUDE.md;
    home.file.".claude/skills" = {
      source = withHomeDir "claude-skills" ./claude/skills;
      recursive = true;
    };
    home.file.".claude/workflows" = {
      source = withHomeDir "claude-workflows" ./claude/workflows;
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

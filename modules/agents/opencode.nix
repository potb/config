{
  inputs,
  lib,
  ...
}: {
  nixos = {};

  darwin = {};

  home = {pkgs, ...}: let
    isLinux = pkgs.stdenv.hostPlatform.isLinux;
    isDarwin = pkgs.stdenv.hostPlatform.isDarwin;

    opencode2 = inputs.llm-agents.packages.${pkgs.stdenv.hostPlatform.system}.opencode2;

    opencode = pkgs.runCommand "opencode-${opencode2.version}" {} ''
      mkdir -p $out/bin
      ln -s ${opencode2}/bin/opencode2 $out/bin/opencode
    '';

    mcpServers =
      {
        sentry = {
          type = "remote";
          url = "https://mcp.sentry.dev/mcp";
        };
      }
      // lib.optionalAttrs isLinux {
        desktop = {
          type = "local";
          command = ["${pkgs.computer-use-linux}/bin/computer-use-linux" "mcp"];
          environment.YDOTOOL_SOCKET = "/run/ydotoold/socket";
        };
      }
      // lib.optionalAttrs isDarwin {
        desktop = {
          type = "local";
          command = ["${pkgs.nodejs}/bin/npx" "-y" "mac-mcp-server@0.1.3"];
        };
      };

    settings = {
      "$schema" = "https://opencode.ai/config.json";
      model = "claude-agent/opus";
      skills = ["~/.claude/skills"];
      providers.claude-agent = {
        name = "Claude";
        models = {
          haiku = {
            name = "Haiku";
            releaseDate = "2026-01-01";
          };
          sonnet = {
            name = "Sonnet";
            releaseDate = "2026-02-02";
            settings.effort = "medium";
          };
          opus = {
            name = "Opus";
            releaseDate = "2026-03-03";
            settings.effort = "medium";
          };
          fable = {
            name = "Fable";
            releaseDate = "2026-04-04";
          };
        };
      };
      providers.vercel-ai = {
        name = "Vercel";
        canonical = "vercel";
        settings.apiKey = "{file:~/.config/herdr-app/data/ai-spend/vercel.key}";
        models = {
          "deepseek-v4.1" = {
            name = "DeepSeek Flash Fast";
            modelID = "deepseek/deepseek-v4.1-flash-fast";
            settings.reasoningEffort = "high";
          };
        };
      };
      policies = [
        {
          action = "provider.use";
          resource = "*";
          effect = "deny";
        }
        {
          action = "provider.use";
          resource = "claude-agent";
          effect = "allow";
        }
        {
          action = "provider.use";
          resource = "vercel-ai";
          effect = "allow";
        }
      ];
      agents = {
        build.model = "claude-agent/opus#medium";
        plan.disabled = true;
      };
      compaction.buffer = 600000;
      permissions = [
        {
          action = "skill";
          resource = "workflow-blocks";
          effect = "deny";
        }
      ];
      mcp.servers = mcpServers;
    };

    settingsFile = pkgs.writeText "opencode-settings.json" (builtins.toJSON settings);
    cliSettingsFile = ./opencode/cli.json;

    modelAllowlist = [
      "claude-agent/haiku"
      "claude-agent/sonnet"
      "claude-agent/opus"
      "claude-agent/fable"
      "vercel-ai/deepseek-v4.1"
    ];

    modelAllowlistPlugin = pkgs.writeText "opencode-model-allowlist.ts" ''
      import { Plugin } from "@opencode/plugin"

      const allowed = new Set(${builtins.toJSON modelAllowlist})

      export default Plugin.define({
        id: "model-allowlist",
        async setup(ctx) {
          await ctx.model.transform((editor) => {
            for (const model of editor.list()) {
              if (!allowed.has(model.providerID + "/" + model.id)) {
                editor.remove(model.providerID, model.id)
              }
            }
          })
        },
      })
    '';

    commentGuardPlugin = pkgs.writeText "opencode-comment-guard.ts" ''
      import { spawnSync } from "node:child_process"
      import { Plugin } from "@opencode/plugin"

      const guard = ${builtins.toJSON ["${pkgs.python3}/bin/python3" "${./claude/hooks/comment-guard.py}"]}

      const claudeTool = { edit: "Edit", write: "Write", patch: "Write", shell: "Bash" }

      const text = (value) => (typeof value === "string" ? value : "")

      const patchFiles = (patch) => {
        const files = []
        for (const line of patch.split("\n")) {
          const header = line.match(/^\*\*\* (?:Add|Update) File: (.+)$/)
          if (header) files.push({ file_path: header[1].trim(), content: [] })
          else if (line.startsWith("+") && files.length > 0) files.at(-1).content.push(line.slice(1))
        }
        return files.map((file) => ({ file_path: file.file_path, content: file.content.join("\n") }))
      }

      const payloads = (tool, input) => {
        if (tool === "shell") return [{ command: text(input.command) }]
        if (tool === "patch") return patchFiles(text(input.patchText ?? input.patch))
        const file_path = text(input.path ?? input.filePath)
        if (tool === "write") return [{ file_path, content: text(input.content) }]
        return [{ file_path, new_string: text(input.newString) }]
      }

      const notice = (event) => {
        const result = spawnSync(guard[0], guard.slice(1), { input: JSON.stringify(event), encoding: "utf8", timeout: 10000 })
        try {
          return JSON.parse(result.stdout || "{}")?.hookSpecificOutput?.additionalContext ?? ""
        } catch {
          return ""
        }
      }

      export default Plugin.define({
        id: "comment-guard",
        async setup(ctx) {
          await ctx.tool.hook("execute.after", async (call) => {
            const tool_name = claudeTool[call.tool]
            if (!tool_name || call.status === "failed") return
            const input = call.input && typeof call.input === "object" ? call.input : {}
            const cwd = text(input.workdir) || ctx.location.directory
            const notices = payloads(call.tool, input)
              .map((tool_input) => notice({ tool_name, tool_input, cwd }))
              .filter((found) => found !== "")
            if (notices.length === 0) return
            await ctx.session.synthetic({ sessionID: call.sessionID, text: notices.join("\n\n") })
          })
        },
      })
    '';

    jq = "${pkgs.jq}/bin/jq";

    legacySettingsKeys = [
      ".provider"
      ".agent"
      ".providers.claude"
      ".providers.vercel"
      ".agents.plan.model"
    ];

    dropLegacySettings = "del(${lib.concatStringsSep ", " legacySettingsKeys})";
  in {
    home.packages = [opencode];

    home.file.".config/opencode/AGENTS.md".source = ./claude/CLAUDE.md;
    home.file.".config/opencode/plugins/model-allowlist.ts".source = modelAllowlistPlugin;
    home.file.".config/opencode/plugins/comment-guard.ts".source = commentGuardPlugin;

    home.activation.opencodeSettings = lib.hm.dag.entryAfter ["writeBoundary"] ''
      dest="$HOME/.config/opencode/opencode.json"
      run mkdir -p "$HOME/.config/opencode"
      if [ -f "$dest" ] && [ ! -L "$dest" ]; then
        tmp="$(mktemp)"
        ${jq} -s '(.[0] | ${dropLegacySettings}) * .[1]' "$dest" ${settingsFile} > "$tmp" && run install -m 0644 "$tmp" "$dest"
        rm -f "$tmp"
      else
        run rm -f "$dest"
        run install -m 0644 ${settingsFile} "$dest"
      fi
    '';

    home.activation.opencodeCliSettings = lib.hm.dag.entryAfter ["writeBoundary"] ''
      dest="$HOME/.config/opencode/cli.json"
      run mkdir -p "$HOME/.config/opencode"
      if [ -f "$dest" ] && [ ! -L "$dest" ]; then
        tmp="$(mktemp)"
        ${jq} -s '.[0] * .[1]' "$dest" ${cliSettingsFile} > "$tmp" && run install -m 0644 "$tmp" "$dest"
        rm -f "$tmp"
      else
        run rm -f "$dest"
        run install -m 0644 ${cliSettingsFile} "$dest"
      fi
    '';
  };
}

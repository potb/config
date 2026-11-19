{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};
  home = {config, ...}: let
    checkout = "${config.home.homeDirectory}/projects/potb/config/modules/dev/herdr";
    appHome = "${config.home.homeDirectory}/.config/herdr-app";
    mods = builtins.attrNames (lib.filterAttrs (_: type: type == "directory") (builtins.readDir ./herdr/mods));
    link = path: config.lib.file.mkOutOfStoreSymlink "${checkout}/${path}";

    reloadOnEdit = pkgs.writeShellApplication {
      name = "herdr-mods-reload";
      runtimeInputs = [pkgs.inotify-tools pkgs.coreutils];
      text = ''
        src=${lib.escapeShellArg "${checkout}/mods"}
        dest=${lib.escapeShellArg "${appHome}/mods"}
        inotifywait -m -r -q \
          -e close_write,moved_to,create,delete \
          --exclude '(\.d\.ts|jsconfig\.json|\.tmp)$' \
          --format '%w%f' "$src" |
          while IFS= read -r changed; do
            name=$(realpath -s --relative-to="$src" "$changed" | cut -d/ -f1)
            if [ -n "$name" ] && [ "$name" != "." ] && [ -L "$dest/$name" ]; then
              touch -h "$dest/$name"
            fi
          done
      '';
    };
  in {
    home.packages = [pkgs.herdr-app];

    home.file =
      lib.listToAttrs (map (name: {
          name = ".config/herdr-app/mods/${name}";
          value.source = link "mods/${name}";
        })
        mods)
      // {
        ".config/herdr-app/tools".source = link "tools";
        ".config/herdr-app/CLAUDE.md".source = ./herdr/herdr-app-agents.md;
      };

    programs.zsh.initContent = ''
      if [[ -n $HC_RUNTIME && -n $CLAUDE_PID ]] && ! kill -0 "$CLAUDE_PID" 2>/dev/null; then
        unset CLAUDECODE CLAUDE_PID CLAUDE_EFFORT CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID \
          CLAUDE_CODE_SESSION_ATTENDED CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH \
          CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN
      fi
    '';

    programs.herdr = {
      enable = true;
      settings = {
        onboarding = false;
        theme.name = "catppuccin-latte";
        terminal.kitty_graphics = true;
        ui = {
          pane_borders = "always";
          pane_outer_borders = true;
        };
        update = {
          version_check = false;
          manifest_check = false;
        };
      };
    };

    linux.systemd.user.services.herdr-mods-reload = {
      Unit.Description = "Reload herdr mods when their checkout files change";
      Service = {
        ExecStart = lib.getExe reloadOnEdit;
        Restart = "always";
        RestartSec = 5;
      };
      Install.WantedBy = ["default.target"];
    };
  };
}

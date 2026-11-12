{pkgs, ...}: {
  nixos = {};
  darwin = {};
  home = {
    home.packages = [pkgs.herdr-app];

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
  };
}

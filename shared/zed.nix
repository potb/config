# Shared Zed editor configuration
# Used by both home-manager and flake app output
{pkgs}: let
  fonts = import ./fonts.nix {inherit pkgs;};
in {
  settings = {
    # OpenCode ACP agent server
    agent_servers = {
      OpenCode = {
        command = "${pkgs.opencode}/bin/opencode";
        args = ["acp"];
      };
    };

    # Disable all AI features - use opencode instead
    features = {
      copilot = false;
    };
    assistant = {
      enabled = false;
    };

    project_panel = {
      hide_gitignore = true;
    };

    # Fonts from shared/fonts.nix
    # Sizes match VSCode/Cursor defaults (14px editor, 14px terminal)
    buffer_font_family = fonts.monospace.name;
    buffer_font_size = 14;
    ui_font_family = fonts.ui.name;
    ui_font_size = 14;
    terminal = {
      font_family = fonts.monospace.name;
      font_size = 14;
    };

    base_keymap = "JetBrains";

    # Theme from catppuccin extension
    theme = {
      mode = "system";
      light = "Catppuccin Latte";
      dark = "Catppuccin Mocha";
    };

    # Icons from catppuccin-icons extension
    icon_theme = "Catppuccin Latte";
  };
}

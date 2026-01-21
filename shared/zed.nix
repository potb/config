# Shared Zed editor configuration
# Used by both home-manager and flake app output
{ pkgs }:
let
  fonts = import ./fonts.nix { inherit pkgs; };
in
{
  settings = {
    # OpenCode ACP agent server
    agent_servers = {
      OpenCode = {
        command = "${pkgs.opencode}/bin/opencode";
        args = [ "acp" ];
      };
    };

    # Disable all AI features - use opencode instead
    features = {
      copilot = false;
    };
    assistant = {
      enabled = false;
    };

    # UI cleanup - minimalist interface
    title_bar = {
      show_onboarding_banner = false;
      show_project_items = false;
      show_branch_name = false;
      show_user_menu = false;
    };
    tab_bar = {
      show = false;
    };
    toolbar = {
      quick_actions = false;
    };
    status_bar = {
      "experimental.show" = false;
    };
    project_panel = {
      dock = "right";
      default_width = 400;
      hide_root = true;
      auto_fold_dirs = false;
      starts_open = false;
      git_status = false;
      sticky_scroll = false;
      hide_gitignore = true;
      scrollbar = {
        show = "never";
      };
      indent_guides = {
        show = "never";
      };
    };
    outline_panel = {
      default_width = 300;
      indent_guides = {
        show = "never";
      };
    };
    file_finder = {
      modal_max_width = "large";
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

    # Theme from catppuccin extension
    theme = {
      mode = "system";
      light = "Catppuccin Latte";
      dark = "Catppuccin Mocha";
    };

    # Icons from catppuccin-icons extension
    icon_theme = "Catppuccin Latte";
  };

  keymaps = [
    {
      bindings = {
        "alt-1" = "workspace::ToggleRightDock";
      };
    }
  ];
}

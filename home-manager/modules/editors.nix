{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../../shared/fonts.nix {inherit pkgs;};
in {
  programs.nixvim = {
    enable = true;
    defaultEditor = true;
    viAlias = true;
    vimAlias = true;
    man.enable = false;

    opts = {
      number = true;
      relativenumber = true;
      clipboard = "unnamedplus";
    };

    colorschemes.catppuccin = {
      enable = true;
      settings.flavour = "latte";
    };

    plugins.web-devicons.enable = true;
    plugins.treesitter.enable = true;

    plugins.telescope = {
      enable = true;
      extensions.fzf-native.enable = true;
      keymaps = {
        "<leader>ff" = "find_files";
        "<leader>fg" = "live_grep";
      };
      keymapsSilent = true;
    };

    plugins.which-key.enable = true;

    plugins.lsp = {
      enable = true;
      keymaps = {
        silent = true;
        lspBuf = {
          "gd" = "definition";
          "gr" = "references";
          "K" = "hover";
          "<leader>rn" = "rename";
        };
      };
      servers = {
        nil_ls.enable = true;
        lua_ls.enable = true;
        ts_ls.enable = true;
        pyright.enable = true;
      };
    };
  };

  programs.alacritty = {
    enable = true;
    settings = {
      font = {
        normal = {
          family = lib.mkForce fonts.monospace.name;
          style = "Regular";
        };
        bold = {
          family = lib.mkForce fonts.monospace.name;
          style = "Bold";
        };
        italic = {
          family = lib.mkForce fonts.monospace.name;
          style = "Italic";
        };
        size = lib.mkForce fonts.sizes.medium;
      };
      general.live_config_reload = true;
    };
  };

  stylix.targets.zed.enable = false;

  programs.zed-editor = {
    enable = true;
    mutableUserSettings = false;
    mutableUserKeymaps = false;
    mutableUserTasks = false;
    extensions = [
      "catppuccin"
      "catppuccin-icons"
      "nix"
    ];
    userSettings = {
      agent_servers = {
        OpenCode = {
          type = "custom";
          command = "${pkgs.opencode}/bin/opencode";
          args = ["acp"];
        };
      };

      features.edit_prediction_provider = "none";
      agent.enabled = true;

      title_bar = {
        show_onboarding_banner = false;
        show_project_items = false;
        show_branch_name = false;
        show_user_menu = false;
        show_menus = false;
      };
      tab_bar.show = false;
      toolbar.quick_actions = false;
      status_bar."experimental.show" = false;
      project_panel = {
        dock = "right";
        default_width = 400;
        hide_root = true;
        auto_fold_dirs = false;
        starts_open = false;
        git_status = false;
        sticky_scroll = false;
        hide_gitignore = true;
        scrollbar.show = "never";
        indent_guides.show = "never";
      };
      outline_panel = {
        default_width = 300;
        indent_guides.show = "never";
      };
      file_finder.modal_max_width = "large";

      buffer_font_family = fonts.monospace.name;
      buffer_font_size = fonts.sizes.large;
      ui_font_family = fonts.ui.name;
      ui_font_size = fonts.sizes.large;
      terminal = {
        font_family = fonts.monospace.name;
        font_size = fonts.sizes.large;
      };

      theme = {
        mode = "system";
        light = "Catppuccin Latte";
        dark = "Catppuccin Mocha";
      };
      icon_theme = "Catppuccin Latte";
    };
    userKeymaps = [
      {
        bindings = {
          "alt-1" = "project_panel::ToggleFocus";
          "alt-2" = "agent::ToggleFocus";
        };
      }
    ];
  };

  home.packages = with pkgs; [
    opencode
  ];
}

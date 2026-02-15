{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../../shared/fonts.nix {inherit pkgs;};
in {
  programs.neovim = {
    enable = true;
    defaultEditor = true;
    viAlias = true;
    vimAlias = true;
    plugins = with pkgs.vimPlugins; [
      nvim-lspconfig
      nvim-treesitter.withAllGrammars
      plenary-nvim
      mini-nvim
      telescope-nvim
      telescope-fzf-native-nvim
      which-key-nvim
      catppuccin-nvim
    ];
    extraPackages = with pkgs; [
      nil
      lua-language-server
      nodePackages.typescript-language-server
      pyright
    ];
    initLua = ''
      -- Colorscheme
      vim.cmd.colorscheme "catppuccin-latte"

      -- Basic options
      vim.opt.number = true
      vim.opt.relativenumber = true
      vim.opt.clipboard = "unnamedplus"

      -- LSP keybindings
      local on_attach = function(client, bufnr)
        local opts = { noremap = true, silent = true, buffer = bufnr }
        vim.keymap.set("n", "gd", vim.lsp.buf.definition, opts)
        vim.keymap.set("n", "gr", vim.lsp.buf.references, opts)
        vim.keymap.set("n", "K", vim.lsp.buf.hover, opts)
        vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename, opts)
      end

      -- Setup LSP servers
      local lspconfig = require("lspconfig")
      lspconfig.nil_ls.setup { on_attach = on_attach }
      lspconfig.lua_ls.setup { on_attach = on_attach }
      lspconfig.tsserver.setup { on_attach = on_attach }
      lspconfig.pyright.setup { on_attach = on_attach }

      -- Telescope keybindings
      local telescope = require("telescope.builtin")
      vim.keymap.set("n", "<leader>ff", telescope.find_files, { noremap = true, silent = true })
      vim.keymap.set("n", "<leader>fg", telescope.live_grep, { noremap = true, silent = true })

      -- Which-key setup
      require("which-key").setup {}
    '';
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

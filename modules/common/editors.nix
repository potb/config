{...}: {
  nixos = {};
  darwin = {};
  home = {
    programs.nixvim = {
      enable = true;
      defaultEditor = true;
      viAlias = true;
      vimAlias = true;
      enableMan = false;

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
          "<leader>ff" = {
            action = "find_files";
            options.silent = true;
          };
          "<leader>fg" = {
            action = "live_grep";
            options.silent = true;
          };
        };
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
  };
}

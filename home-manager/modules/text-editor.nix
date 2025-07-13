{...}: {
  programs.nixvim.enable = true;
  programs.nixvim.defaultEditor = true;

  programs.nixvim.extraConfigLua = ''
         vim.diagnostic.config({
    update_in_insert = true,
         })

         -- Set diagnostic symbols to an empty string or space
         vim.fn.sign_define("DiagnosticSignError", {text = "", texthl = "DiagnosticSignError"})
         vim.fn.sign_define("DiagnosticSignWarn", {text = "", texthl = "DiagnosticSignWarn"})
         vim.fn.sign_define("DiagnosticSignInfo", {text = "", texthl = "DiagnosticSignInfo"})
         vim.fn.sign_define("DiagnosticSignHint", {text = "", texthl = "DiagnosticSignHint"})
  '';

  programs.nixvim.plugins = {
    lightline.enable = true;

    web-devicons.enable = true;

    telescope.enable = true;

    cmp = {
      enable = true;

      settings = {
        autoEnableSources = true;

        sources = [
          {name = "nvim_lsp";}
          {
            name = "buffer";
            option.get_bufnrs.__raw = "vim.api.nvim_list_bufs";
            keywordLength = 3;
          }
          {
            name = "path";
            keywordLength = 3;
          }
        ];
      };
    };

    cmp-buffer.enable = true;
    cmp-path.enable = true;
    cmp-cmdline.enable = true;
    cmp-nvim-lsp.enable = true;
    cmp-nvim-lsp-document-symbol.enable = true;
    cmp-nvim-lsp-signature-help.enable = true;

    lsp = {
      enable = true;
      servers = {
        nixd.enable = true;
        ts_ls.enable = true;
      };
    };
  };

  programs.nixvim.colorschemes.catppuccin.enable = true;
  programs.nixvim.colorschemes.catppuccin.settings.flavour = "latte";

  programs.nixvim.opts = {
    number = true;
    relativenumber = true;
    expandtab = true;
  };
}

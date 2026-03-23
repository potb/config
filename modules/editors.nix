{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../shared/fonts.nix {inherit pkgs;};
  claudeCodeVersion = pkgs.claude-code.version;
  claudeCodeUserAgent = "claude-cli/${claudeCodeVersion} (external, cli)";
  idea-vmoptions = pkgs.writeText "idea64.vmoptions" ''
    -Dawt.toolkit.name=WLToolkit
  '';
  idea-wrapped = pkgs.symlinkJoin {
    name = "idea";
    paths = [pkgs.jetbrains.idea];
    nativeBuildInputs = [pkgs.makeWrapper];
    postBuild = ''
      wrapProgram $out/bin/idea \
        --set-default IDEA_VM_OPTIONS ${idea-vmoptions}
    '';
  };
  opencode-wrapped = pkgs.symlinkJoin {
    name = "opencode";
    paths = [pkgs.opencode];
    nativeBuildInputs = [pkgs.makeWrapper];
    postBuild = ''
      wrapProgram $out/bin/opencode \
        --set-default ANTHROPIC_CLI_VERSION '${claudeCodeVersion}' \
        --set-default ANTHROPIC_ENABLE_1M_CONTEXT true \
        --set-default ANTHROPIC_USER_AGENT '${claudeCodeUserAgent}' \
        --prefix PATH : ${
        pkgs.lib.makeBinPath [
          pkgs.claude-code
          pkgs.nodePackages.typescript
          pkgs.nodePackages.typescript-language-server
          pkgs.pyright
          pkgs.nixd
          pkgs.nodePackages.vscode-langservers-extracted
        ]
      }
    '';
  };
in {
  nixos = {};
  darwin = {};
  home = {
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

    home.packages = [
      opencode-wrapped
      pkgs.claude-code
      idea-wrapped
    ];
  };
}

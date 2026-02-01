{
  pkgs,
  inputs,
  lib,
  config,
  mkZedConfig,
  ...
}: let
  zedConfig = mkZedConfig pkgs;
in {
  imports = [./shell.nix];
  # Font configuration (Linux only - macOS uses system font management)
  fonts.fontconfig.enable = pkgs.stdenv.isLinux;

  # Workaround for home-manager bug #7352 on Darwin
  # Disable broken Darwin modules that pull in glibc
  home.file."Library/Fonts/.home-manager-fonts-version" = lib.mkIf pkgs.stdenv.isDarwin {
    enable = lib.mkForce false;
  };
  home.file."Applications/Home Manager Apps" = lib.mkIf pkgs.stdenv.isDarwin {
    enable = lib.mkForce false;
  };

  programs = {
    git = {
      enable = true;

      settings = {
        user = {
          name = "Peïo Thibault";
          email = "peio.thibault@gmail.com";
        };
      };

      includes = [{path = "${inputs.catppuccin-delta}/themes/latte.gitconfig";}];
    };

    delta = {
      enable = true;
      enableGitIntegration = true;

      options = {
        features = "catppuccin-latte";
      };
    };

    eza = {
      enable = true;
      enableZshIntegration = true;
    };

    bat = {
      enable = true;
    };

    ripgrep = {
      enable = true;
    };

    zoxide = {
      enable = true;
    };

    gh = {
      enable = true;
      settings = {
        git_protocol = "ssh";
        prompt = "enabled";
        pager = "${pkgs.bat}/bin/bat";
      };
    };

    jq = {
      enable = true;
    };

    neovim = {
      enable = true;
      defaultEditor = true;
      viAlias = true;
      vimAlias = true;

      plugins = with pkgs.vimPlugins; [
        nvim-lspconfig
        nvim-treesitter.withAllGrammars
        plenary-nvim
        mini-nvim
      ];
    };

    alacritty = {
      enable = true;

      settings = {
        font = {
          normal = {
            family = lib.mkForce "FiraCode Nerd Font Mono";
            style = "Regular";
          };
          bold = {
            family = lib.mkForce "FiraCode Nerd Font Mono";
            style = "Bold";
          };
          italic = {
            family = lib.mkForce "FiraCode Nerd Font Mono";
            style = "Italic";
          };
          size = lib.mkForce 12.0;
        };
        general = {
          live_config_reload = true;
        };
      };
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
    userSettings = zedConfig.settings;
    userKeymaps = zedConfig.keymaps;
  };
}

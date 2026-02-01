{
  pkgs,
  lib,
  mkZedConfig,
  ...
}: let
  zedConfig = mkZedConfig pkgs;
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
    ];
  };

  programs.alacritty = {
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
    userSettings = zedConfig.settings;
    userKeymaps = zedConfig.keymaps;
  };

  home.packages = with pkgs; [
    jetbrains.datagrip
    opencode
  ];
}

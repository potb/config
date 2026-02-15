{
  pkgs,
  lib,
  config,
  ...
}: {
  programs.zsh = {
    enable = true;
    dotDir = "${config.xdg.configHome}/zsh";

    antidote.enable = true;
    antidote.plugins =
      [
        "mattmc3/ez-compinit"
        "zsh-users/zsh-completions kind:fpath path:src"
        "getantidote/use-omz"
        "ohmyzsh/ohmyzsh path:lib"
        "ohmyzsh/ohmyzsh path:plugins/aws"
        "ohmyzsh/ohmyzsh path:plugins/colored-man-pages"
        "ohmyzsh/ohmyzsh path:plugins/common-aliases"
        "ohmyzsh/ohmyzsh path:plugins/docker"
        "ohmyzsh/ohmyzsh path:plugins/docker-compose"
        "ohmyzsh/ohmyzsh path:plugins/extract"
        "ohmyzsh/ohmyzsh path:plugins/eza"
        "ohmyzsh/ohmyzsh path:plugins/fancy-ctrl-z"
        "ohmyzsh/ohmyzsh path:plugins/git"
        "ohmyzsh/ohmyzsh path:plugins/gpg-agent"
        "ohmyzsh/ohmyzsh path:plugins/magic-enter"
        "ohmyzsh/ohmyzsh path:plugins/node"
        "ohmyzsh/ohmyzsh path:plugins/ssh"
        "ohmyzsh/ohmyzsh path:plugins/ssh-agent"
        "ohmyzsh/ohmyzsh path:plugins/sudo"
        "ohmyzsh/ohmyzsh path:plugins/starship"
        "ohmyzsh/ohmyzsh path:plugins/transfer"
        "ohmyzsh/ohmyzsh path:plugins/zoxide"
        "zsh-users/zsh-autosuggestions"
        "zdharma-continuum/fast-syntax-highlighting"
      ]
      ++ lib.optionals pkgs.stdenv.isLinux [
        "ohmyzsh/ohmyzsh path:plugins/systemd"
      ];

    initContent = lib.mkBefore ''
      zstyle ':omz:plugins:eza' 'dirs-first' yes
      zstyle ':omz:plugins:eza' 'git-status' yes
      zstyle ':omz:plugins:eza' 'header' yes
      zstyle ':omz:plugins:eza' 'icons' yes

      export MAGIC_ENTER_OTHER_COMMAND='ls -lah .'

      eval "$(${pkgs.fnm}/bin/fnm env --use-on-cd --version-file-strategy=recursive --corepack-enabled --resolve-engines)"
    '';

    shellAliases = {
      cd = "z";
    };
  };

  programs.starship = {
    enable = true;
    settings = {
      username = {
        disabled = false;
        show_always = true;
      };
      hostname = {
        ssh_only = false;
      };
    };
  };

  programs.mcfly.enable = true;

  programs.zoxide.enable = true;
}

{
  inputs,
  system,
  pkgs,
  lib,
  ...
}: {
  # Global theme
  catppuccin = {
    enable = true;
    flavor = "latte";
  };

  home.file.".zsh_plugins.txt".text = ''
    mattmc3/ez-compinit
    zsh-users/zsh-completions kind:fpath path:src
    getantidote/use-omz
    ohmyzsh/ohmyzsh path:lib
    ohmyzsh/ohmyzsh path:plugins/archlinux
    ohmyzsh/ohmyzsh path:plugins/aws kind:defer
    ohmyzsh/ohmyzsh path:plugins/bun kind:defer
    ohmyzsh/ohmyzsh path:plugins/colored-man-pages kind:defer
    ohmyzsh/ohmyzsh path:plugins/common-aliases
    ohmyzsh/ohmyzsh path:plugins/docker
    ohmyzsh/ohmyzsh path:plugins/docker-compose
    ohmyzsh/ohmyzsh path:plugins/extract
    ohmyzsh/ohmyzsh path:plugins/eza
    ohmyzsh/ohmyzsh path:plugins/fancy-ctrl-z
    ohmyzsh/ohmyzsh path:plugins/git
    ohmyzsh/ohmyzsh path:plugins/git-commit kind:defer
    ohmyzsh/ohmyzsh path:plugins/gpg-agent
    ohmyzsh/ohmyzsh path:plugins/heroku kind:defer
    ohmyzsh/ohmyzsh path:plugins/magic-enter
    ohmyzsh/ohmyzsh path:plugins/node kind:defer
    ohmyzsh/ohmyzsh path:plugins/ssh kind:defer
    ohmyzsh/ohmyzsh path:plugins/ssh-agent
    ohmyzsh/ohmyzsh path:plugins/sudo
    ohmyzsh/ohmyzsh path:plugins/starship
    ohmyzsh/ohmyzsh path:plugins/systemd
    ohmyzsh/ohmyzsh path:plugins/transfer kind:defer
    ohmyzsh/ohmyzsh path:plugins/zoxide
    zsh-users/zsh-autosuggestions
    zdharma-continuum/fast-syntax-highlighting kind:defer
  '';

  home = let
    homePath = "/home/potb";
  in {
    packages =
      (
        with pkgs; [
          fnm
          act
          duf
          du-dust
          fd
          glow
          httpie
          spotify
          google-chrome
        ]
      )
      ++ [inputs.nh.packages.${pkgs.system}.nh];

    sessionVariables = {
      NH_FLAKE = "${homePath}/projects/potb/config";
    };
  };

  programs = {
    zsh = {
      enable = true;
      enableCompletion = true;
      autosuggestion.enable = true;
      syntaxHighlighting.enable = true;

      initExtraFirst = "source /etc/zsh/zshrc";

      initExtraFirst = ''
        source /etc/zsh/zshrc
        source '/usr/share/zsh-antidote/antidote.zsh'

        zstyle ':omz:plugins:eza' 'dirs-first' yes
        zstyle ':omz:plugins:eza' 'git-status' yes
        zstyle ':omz:plugins:eza' 'header' yes
        zstyle ':omz:plugins:eza' 'icons' yes
        
	export MAGIC_ENTER_OTHER_COMMAND='ls -lah .'
        
	antidote load
        
	eval "$(${pkgs.fnm}/bin/fnm env --use-on-cd --version-file-strategy=recursive --corepack-enabled --resolve-engines)"

        unalias l
      '';

      oh-my-zsh = {
        enable = true;
        plugins = [
          "git"
          "gitfast"
          "common-aliases"
          "docker"
          "docker-compose"
          "ssh-agent"
        ];
      };

      shellAliases = {
        cd = "z";
      };
    };

    starship = {
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

    mcfly = {
      enable = true;
    };

    git = {
      enable = true;

      userName = "Peïo Thibault";
      userEmail = "peio.thibault@gmail.com";

      includes = [{path = "${inputs.catppuccin-delta}/themes/latte.gitconfig";}];

      delta = {
        enable = true;

        options = {
          features = "catppuccin-latte";
        };
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

    alacritty = {
      enable = true;
      
      settings = {
              font = {
          normal = {
            family = "FiraCode Nerd Font Mono";
            style = "Regular";
          };
          bold = {
            family = "FiraCode Nerd Font Mono";
            style = "Bold";
          };
          italic = {
            family = "FiraCode Nerd Font Mono";
            style = "Italic";
          };
          size = 12.0;
        };
        env = { TERM = "xterm-256color"; };
        general = { live_config_reload = true; };
      };
    };
  };
}

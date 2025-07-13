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

      initExtra = ''
        eval "$(${pkgs.fnm}/bin/fnm env --use-on-cd --version-file-strategy=recursive --corepack-enabled --resolve-engines)"
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

    kitty = {
      enable = true;
      themeFile = "Catppuccin-Latte";
      # font = {
      #   name = "FiraCode Nerd Font Mono";
      #   package = pkgs.nerd-fonts.fira-code;
      # };

      settings = {
        enable_audio_bell = false;
      };
    };
  };
}

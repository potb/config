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
    homePath =
      if pkgs.stdenv.isDarwin
      then "/Users/potb"
      else "/home/potb";
    nixpkgs-master = inputs.nixpkgs-master.legacyPackages.${system};
  in {
    packages =
      (with pkgs;
        [
          fnm
          act
          dogdns
          duf
          du-dust
          docker
          docker-buildx
          docker-compose
          fd
          glow
          httpie
          spotify
          (pulumi-bin.overrideAttrs (old: {
            version = "${old.version}-trimmed";

            srcs = let
              plugins = [
                "pulumi-resource-random"
                "pulumi-resource-tls"
                "pulumi-resource-aws"
              ];

              isPulumiSDK = plugin:
                builtins.match ".*get.pulumi.com/releases/sdk/.*" plugin.url != null;

              isWantedPlugin = plugin:
                lib.any (p: builtins.match ".*${p}.*" plugin.url != null) plugins
                || isPulumiSDK plugin;
            in
              lib.filter isWantedPlugin old.srcs;
          }))
          nixpkgs-master.bun
          google-chrome
          cloudflared
          zed-editor
        ]
        ++ (
          if stdenv.isDarwin
          then [raycast colima]
          else []
        ))
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

{
  inputs,
  pkgs,
  ...
}: {
  nixpkgs = {
    config = {
      allowUnfree = true;
    };
  };

  # Global theme
  catppuccin = {
    enable = true;
    flavor = "latte";
  };

  home = {
    username = "potb";
    homeDirectory =
      if pkgs.stdenv.isDarwin
      then "/Users/potb"
      else "/home/potb";
    packages = with pkgs;
      [
        awscli2
        google-cloud-sdk
        fnm
        act
        dog
        duf
        du-dust
        docker-buildx
        docker-compose
        lazydocker
        dog
        doppler
        fd
        ffmpeg
        glow
        httpie
        sd
        spotify
        steampipe
        step-cli
        terraform
        tokei
        ssm-session-manager-plugin
        yq
        pulumi-bin
        nh
        jetbrains.webstorm
        jetbrains.pycharm-professional
        jetbrains.gateway
      ]
      ++ (
        if stdenv.isDarwin
        then [raycast colima]
        else [google-chrome]
      );

    stateVersion = "24.05";
  };

  xsession.windowManager = {
    i3 = let
      mod = "Mod4";
    in
      if pkgs.stdenv.isDarwin
      then {}
      else {
        enable = true;
        package = pkgs.i3-gaps;
        config = {
          modifier = mod;
          gaps = {
            inner = 10;
            outer = 5;
          };
          fonts = {
            names = ["monospace"];
            size = 9.0;
          };
          bars = [
            {
              position = "bottom";
              fonts = {
                names = ["monospace"];
                size = 10.0;
              };
              hiddenState = "hide";
              statusCommand = "${pkgs.i3status}/bin/i3status";
            }
          ];
        };
        extraConfig = ''
          for_window [class=".*"] border pixel 4
        '';
      };
  };

  programs = {
    home-manager.enable = true;

    vscode = {
      enable = true;
      enableExtensionUpdateCheck = false;
      enableUpdateCheck = false;
      mutableExtensionsDir = true;

      package = pkgs.vscode.fhs;

      extensions = with pkgs.vscode-extensions; [
        ms-vscode-remote.remote-ssh
        ms-python.python
        catppuccin.catppuccin-vsc-icons
        catppuccin.catppuccin-vsc
        github.copilot
        github.copilot-chat
      ];

      userSettings = {
        "workbench.colorTheme" = "Catppuccin Latte";
        "workbench.iconTheme" = "catppuccin-latte";
      };
    };

    zsh = {
      enable = true;
      enableCompletion = true;
      autosuggestion.enable = true;
      syntaxHighlighting.enable = true;

      initExtra = ''
        eval "$(${pkgs.fnm}/bin/fnm env --use-on-cd --corepack-enabled --resolve-engines)"
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

    nixvim = {
      enable = true;
      defaultEditor = true;

      extraConfigLua = ''
        vim.diagnostic.config({
          update_in_insert = true,
        })

        -- Set diagnostic symbols to an empty string or space
        vim.fn.sign_define("DiagnosticSignError", {text = "", texthl = "DiagnosticSignError"})
        vim.fn.sign_define("DiagnosticSignWarn", {text = "", texthl = "DiagnosticSignWarn"})
        vim.fn.sign_define("DiagnosticSignInfo", {text = "", texthl = "DiagnosticSignInfo"})
        vim.fn.sign_define("DiagnosticSignHint", {text = "", texthl = "DiagnosticSignHint"})
      '';

      plugins = {
        lightline.enable = true;

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
            pyright.enable = true;
            tsserver.enable = true;
          };
        };
      };

      colorschemes.catppuccin.enable = true;
      colorschemes.catppuccin.flavour = "latte";

      options = {
        number = true;
        relativenumber = true;
        expandtab = true;
      };
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
      theme = "Catppuccin-Latte";
      font = {
        name = "FiraCode Nerd Font Mono Medium";
        package = pkgs.nerdfonts.override {fonts = ["FiraCode"];};
      };

      settings = {
        enable_audio_bell = false;
      };
    };
  };

  services = {
    vscode-server = {
      enable = true;
    };

    picom = {
      enable = true;

      backend = "glx";

      fade = true;
      fadeDelta = 2;

      settings = {
        xrender-sync-fence = true;
        mark-ovredir-focused = false;
        use-ewmh-active-win = true;

        unredir-if-possible = false;
        backend = "xrender";
        vsync = true;

        corner-radius = 15.0;
        round-border = 15.0;
      };
    };
  };
}

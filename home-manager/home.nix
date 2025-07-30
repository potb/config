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

  xdg = {
    enable = true;

    mimeApps = {
      enable = true;
      defaultApplications = let
        vlc = "vlc.desktop";
        chrome = "google-chrome.desktop";
      in {
        "audio/*" = [vlc];
        "video/*" = [vlc];

        "x-scheme-handler/http" = [chrome];
        "x-scheme-handler/https" = [chrome];
        "text/html" = [chrome];
      };
    };

    portal = {
      enable = true;
      extraPortals = [pkgs.xdg-desktop-portal-gtk];
      xdgOpenUsePortal = true;
      config.common.default = "*";
    };
  };

  xsession.windowManager = {
    i3 = let
      mod = "Mod4";
    in {
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

        keybindings = {
          "${mod}+Return" = "exec alacritty";
          "${mod}+p" = "exec rofi -show drun";
          "${mod}+w" = "exec google-chrome-stable";
          "${mod}+e" = "exec alacritty -e yazi";
          "Print" = "exec --no-startup-id sh -c 'maim -s | xclip -selection clipboard -t image/png'";

          "${mod}+Shift+Escape" = "exit";
          "${mod}+BackSpace" = "kill";
          "${mod}+f" = "fullscreen toggle";
          "${mod}+Shift+space" = "floating toggle";
          "${mod}+space" = "floating toggle";
          "${mod}+Shift+r" = "reload";

          "${mod}+h" = "split h";
          "${mod}+v" = "split v";

          "${mod}+Left" = "focus left";
          "${mod}+Down" = "focus down";
          "${mod}+Up" = "focus up";
          "${mod}+Right" = "focus right";

          "${mod}+Shift+Left" = "move left";
          "${mod}+Shift+Down" = "move down";
          "${mod}+Shift+Up" = "move up";
          "${mod}+Shift+Right" = "move right";

          "${mod}+1" = "workspace \"1\"";
          "${mod}+2" = "workspace \"2\"";
          "${mod}+3" = "workspace \"3\"";
          "${mod}+4" = "workspace \"4\"";
          "${mod}+5" = "workspace \"5\"";
          "${mod}+6" = "workspace \"6\"";
          "${mod}+7" = "workspace \"7\"";
          "${mod}+8" = "workspace \"8\"";
          "${mod}+9" = "workspace \"9\"";
          "${mod}+0" = "workspace \"10\"";

          "${mod}+Shift+1" = "move container to workspace \"1\"";
          "${mod}+Shift+2" = "move container to workspace \"2\"";
          "${mod}+Shift+3" = "move container to workspace \"3\"";
          "${mod}+Shift+4" = "move container to workspace \"4\"";
          "${mod}+Shift+5" = "move container to workspace \"5\"";
          "${mod}+Shift+6" = "move container to workspace \"6\"";
          "${mod}+Shift+7" = "move container to workspace \"7\"";
          "${mod}+Shift+8" = "move container to workspace \"8\"";
          "${mod}+Shift+9" = "move container to workspace \"9\"";
          "${mod}+Shift+0" = "move container to workspace \"10\"";

          "${mod}+Ctrl+1" = "move container to workspace \"1\"; workspace \"1\"";
          "${mod}+Ctrl+2" = "move container to workspace \"2\"; workspace \"2\"";
          "${mod}+Ctrl+3" = "move container to workspace \"3\"; workspace \"3\"";
          "${mod}+Ctrl+4" = "move container to workspace \"4\"; workspace \"4\"";
          "${mod}+Ctrl+5" = "move container to workspace \"5\"; workspace \"5\"";
          "${mod}+Ctrl+6" = "move container to workspace \"6\"; workspace \"6\"";
          "${mod}+Ctrl+7" = "move container to workspace \"7\"; workspace \"7\"";
          "${mod}+Ctrl+8" = "move container to workspace \"8\"; workspace \"8\"";
          "${mod}+Ctrl+9" = "move container to workspace \"9\"; workspace \"9\"";
          "${mod}+Ctrl+0" = "move container to workspace \"10\"; workspace \"10\"";
        };
      };

      extraConfig = ''
        for_window [class=".*"] border pixel 4
      '';
    };
  };

  programs = {
    zsh = {
      enable = true;

      antidote.enable = true;
      antidote.plugins = [
        "mattmc3/ez-compinit"
        "zsh-users/zsh-completions kind:fpath path:src"
        "getantidote/use-omz"
        "ohmyzsh/ohmyzsh path:lib"
        "ohmyzsh/ohmyzsh path:plugins/archlinux"
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
        "ohmyzsh/ohmyzsh path:plugins/systemd"
        "ohmyzsh/ohmyzsh path:plugins/transfer"
        "ohmyzsh/ohmyzsh path:plugins/zoxide"
        "zsh-users/zsh-autosuggestions"
        "zdharma-continuum/fast-syntax-highlighting"
      ];

      initExtraFirst = ''
        zstyle ':omz:plugins:eza' 'dirs-first' yes
        zstyle ':omz:plugins:eza' 'git-status' yes
        zstyle ':omz:plugins:eza' 'header' yes
        zstyle ':omz:plugins:eza' 'icons' yes

        export MAGIC_ENTER_OTHER_COMMAND='ls -lah .'

        eval "$(${pkgs.fnm}/bin/fnm env --use-on-cd --version-file-strategy=recursive --corepack-enabled --resolve-engines)"

        unalias l
      '';

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
        general = {live_config_reload = true;};
      };
    };

    yazi = {
      enable = true;
    };

    rofi = {
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
  };

  services = {
    picom = {
      enable = true;
      backend = "glx";
      vSync = true;
      shadow = true;
      fade = true;
      inactiveOpacity = 0.9;
      fadeDelta = 5;

      settings = {
        unredir-if-possible = false;
      };
    };

    dunst = {
      enable = true;
      settings = {
        global.font = "Inter 10";
      };
    };
  };
}

{
  pkgs,
  inputs,
  lib,
  config,
  ...
}: {
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
    zsh = {
      enable = true;
      dotDir = "${config.xdg.configHome}/zsh";

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

      initContent = lib.mkMerge [
        (lib.mkBefore ''
          zstyle ':omz:plugins:eza' 'dirs-first' yes
          zstyle ':omz:plugins:eza' 'git-status' yes
          zstyle ':omz:plugins:eza' 'header' yes
          zstyle ':omz:plugins:eza' 'icons' yes

          export MAGIC_ENTER_OTHER_COMMAND='ls -lah .'

          eval "$(${pkgs.fnm}/bin/fnm env --use-on-cd --version-file-strategy=recursive --corepack-enabled --resolve-engines)"
        '')

        (lib.mkAfter ''
          # ============================================
          # Worktree-first workflow
          # Layout: repo/../worktrees/repo-name/branch-name
          # ============================================

          # Unalias OMZ git plugin aliases first
          unalias gco 2>/dev/null || true
          unalias gcb 2>/dev/null || true

          # Create new branch with worktree
          gwtn() {
            local branch="$1"
            local base="''${2:-$(git_main_branch)}"
            if [[ -z "$branch" ]]; then
              echo "Usage: gwtn <branch-name> [base-branch]"
              return 1
            fi
            local main_wt=$(git worktree list | head -1 | awk '{print $1}')
            local repo_name=$(basename "$main_wt")
            local wt_dir="$(dirname "$main_wt")/worktrees/''${repo_name}/''${branch}"
            mkdir -p "$(dirname "$wt_dir")"
            git worktree add -b "$branch" "$wt_dir" "$base" && cd "$wt_dir"
          }

          # Add worktree for existing branch (e.g., PR review)
          gwtc() {
            local branch="$1"
            if [[ -z "$branch" ]]; then
              echo "Usage: gwtc <branch-name>"
              return 1
            fi
            local main_wt=$(git worktree list | head -1 | awk '{print $1}')
            local repo_name=$(basename "$main_wt")
            local wt_dir="$(dirname "$main_wt")/worktrees/''${repo_name}/''${branch}"
            mkdir -p "$(dirname "$wt_dir")"
            git worktree add "$wt_dir" "$branch" && cd "$wt_dir"
          }

          # Switch to worktree (fuzzy with fzf if available)
          gwts() {
            local target="$1"
            if [[ -z "$target" ]]; then
              if command -v fzf &>/dev/null; then
                target=$(git worktree list | fzf --height 40% | awk '{print $1}')
              else
                git worktree list
                return
              fi
            else
              target=$(git worktree list | grep "$target" | head -1 | awk '{print $1}')
            fi
            [[ -n "$target" ]] && cd "$target"
          }

          # Go to main worktree
          gwtm() {
            local main_wt=$(git worktree list | head -1 | awk '{print $1}')
            [[ -n "$main_wt" ]] && cd "$main_wt"
          }

          # CD to worktree by branch name (direct, no fzf)
          gwcd() {
            local branch="$1"
            if [[ -z "$branch" ]]; then
              echo "Usage: gwcd <branch-name>"
              echo "Tip: Use gwts for interactive fzf selection"
              return 1
            fi
            local wt_path=$(git worktree list | grep "\[$branch\]" | awk '{print $1}')
            if [[ -n "$wt_path" ]]; then
              cd "$wt_path"
            else
              echo "No worktree found for branch: $branch"
              return 1
            fi
          }

          # Remove worktree and optionally delete branch
          gwtd() {
            local branch="$1"
            local delete_branch="''${2:---keep}"
            if [[ -z "$branch" ]]; then
              echo "Usage: gwtd <branch-name> [--delete-branch]"
              return 1
            fi
            local wt_path=$(git worktree list | grep "\\[$branch\\]" | awk '{print $1}')
            if [[ -n "$wt_path" ]]; then
              # Go to main worktree first if we're in the one being deleted
              [[ "$PWD" == "$wt_path"* ]] && gwtm
              git worktree remove "$wt_path"
              [[ "$delete_branch" == "--delete-branch" ]] && git branch -d "$branch"
            else
              echo "Worktree for branch '$branch' not found"
            fi
          }

          # Smart gco wrapper: blocks branch switching, allows file restoration
          # gco branch        -> BLOCKED (use gwtn/gwtc)
          # gco branch -- file -> ALLOWED (file restoration)
          gco() {
            local has_dashdash=0
            for arg in "$@"; do
              [[ "$arg" == "--" ]] && has_dashdash=1 && break
            done

            if (( has_dashdash )); then
              command git checkout "$@"
            else
              echo "Use gwtn (new branch) or gwtc (existing) for worktree-first workflow"
              echo "For file restoration: gco <branch> -- <file>"
              return 1
            fi
          }

          # Block gcb entirely
          gcb() {
            echo "Use gwtn for creating new branches with worktrees"
            return 1
          }
        '')
      ];

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
        general = {live_config_reload = true;};
      };
    };
  };
}

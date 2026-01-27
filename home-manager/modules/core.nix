{
  pkgs,
  inputs,
  lib,
  config,
  mkZedConfig,
  ...
}:
let
  zedConfig = mkZedConfig pkgs;
in
{
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
          unalias gco 2>/dev/null || true
          unalias gcb 2>/dev/null || true

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

          gwtm() {
            local main_wt=$(git worktree list | head -1 | awk '{print $1}')
            [[ -n "$main_wt" ]] && cd "$main_wt"
          }

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

          gwtd() {
            local branch="$1"
            local delete_branch="''${2:---keep}"
            if [[ -z "$branch" ]]; then
              echo "Usage: gwtd <branch-name> [--delete-branch]"
              return 1
            fi
            local wt_path=$(git worktree list | grep "\\[$branch\\]" | awk '{print $1}')
            if [[ -n "$wt_path" ]]; then
              [[ "$PWD" == "$wt_path"* ]] && gwtm
              git worktree remove "$wt_path"
              [[ "$delete_branch" == "--delete-branch" ]] && git branch -d "$branch"
            else
              echo "Worktree for branch '$branch' not found"
            fi
          }

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

          gcb() {
            echo "Use gwtn for creating new branches with worktrees"
            return 1
          }

          gwtclean() {
            local dry_run=0
            [[ "$1" == "--dry-run" || "$1" == "-n" ]] && dry_run=1

            local main_wt=$(git worktree list | head -1 | awk '{print $1}')

            git worktree list | tail -n +2 | while read -r line; do
              local wt_path=$(echo "$line" | awk '{print $1}')
              local branch=$(echo "$line" | grep -o '\[.*\]' | tr -d '[]')

              [[ -z "$branch" ]] && continue

              local pr_state=$(gh pr view "$branch" --json state --jq '.state' 2>/dev/null)

              if [[ "$pr_state" == "MERGED" ]]; then
                if (( dry_run )); then
                  echo "[dry-run] Would remove: $wt_path ($branch) - PR merged"
                else
                  echo "Removing: $wt_path ($branch) - PR merged"
                  [[ "$PWD" == "$wt_path"* ]] && cd "$main_wt"
                  git worktree remove "$wt_path"
                  git branch -d "$branch" 2>/dev/null || git branch -D "$branch"
                fi
              elif [[ -z "$pr_state" ]]; then
                echo "Skipping: $branch - no PR found"
              else
                echo "Skipping: $branch - PR state: $pr_state"
              fi
            done
          }

          _gwt_branches() {
            local branches
            branches=(''${(f)"$(git worktree list 2>/dev/null | awk '{print $3}' | tr -d '[]')"})
            _describe 'branch' branches
          }

          _gwt_all_branches() {
            local branches
            branches=(''${(f)"$(git branch -a 2>/dev/null | sed 's/^[* ]*//' | sed 's|remotes/origin/||' | sort -u)"})
            _describe 'branch' branches
          }

          _gwtn_complete() {
            local -a branches
            if (( CURRENT == 3 )); then
              branches=(''${(f)"$(git branch -a 2>/dev/null | sed 's/^[* ]*//' | sed 's|remotes/origin/||' | sort -u)"})
              _describe 'base branch' branches
            fi
          }

          compdef _gwt_branches gwcd gwtd gwts
          compdef _gwt_all_branches gwtc
          compdef _gwtn_complete gwtn

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

      includes = [ { path = "${inputs.catppuccin-delta}/themes/latte.gitconfig"; } ];
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

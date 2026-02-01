{
  pkgs,
  lib,
  inputs,
  ...
}: {
  programs.git = {
    enable = true;
    settings = {
      user = {
        name = "Peïo Thibault";
        email = "peio.thibault@gmail.com";
      };
    };
    includes = [{path = "${inputs.catppuccin-delta}/themes/latte.gitconfig";}];
  };

  programs.delta = {
    enable = true;
    enableGitIntegration = true;
    options = {
      features = "catppuccin-latte";
    };
  };

  home.packages = with pkgs; [
    git-lfs
    git-filter-repo
  ];

  programs.zsh.initContent = lib.mkAfter ''
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
  '';
}

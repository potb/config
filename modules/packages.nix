{
  pkgs,
  lib,
  ...
}: {
  nixos = {};
  darwin = {};
  home = {
    programs.eza = {
      enable = true;
      enableZshIntegration = true;
    };

    programs.bat.enable = true;
    programs.ripgrep.enable = true;

    programs.gh = {
      enable = true;
      settings = {
        git_protocol = "ssh";
        prompt = "enabled";
        pager = "${pkgs.bat}/bin/bat";
      };
    };

    programs.jq.enable = true;

    home.packages = with pkgs;
      [
        fd
        fzf
        duf
        dust
        glow
        httpie
        tokei
        bottom
        htop
        act
        ffmpeg
        lefthook
        _1password-cli

        age
        croc
        hyperfine
        lnav
        nmap
        rsync
        yt-dlp

        ast-grep
        (d2.override {withImageSupport = false;})
        shellcheck
        shfmt
        tectonic

        duckdb
        harlequin
        postgresql_18

        glab
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux [
        gcc
        binutils
        libnotify
        lm_sensors
        audacity
        prismlauncher
        # Real default zip handler (see modules/wayland.nix mimeApps): without
        # this installed, Prism Launcher is the only application/zip claimant
        # and wins by default even for plain archives.
        xarchiver
        rusty-path-of-building
        vlc
        spotify
        slack
        discord
        jetbrains.datagrip
      ]
      ++ lib.optionals pkgs.stdenv.hostPlatform.isDarwin [
        stdenv.cc

        # Apple Silicon power and sensor readouts; aarch64-darwin only.
        macmon
        mactop

        mermaid-cli
        firebase-tools
        gitlab-ci-local
      ];

    home.sessionVariables =
      {
        EDITOR = "nvim";
      }
      // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
        XDG_DATA_DIRS = "$HOME/Desktop:$XDG_DATA_DIRS";
      }
      // lib.optionalAttrs pkgs.stdenv.hostPlatform.isDarwin {
        BROWSER = lib.mkForce "open -a 'Google Chrome'";
        CC = "${pkgs.stdenv.cc}/bin/cc";
        CXX = "${pkgs.stdenv.cc}/bin/c++";
      };

    home.stateVersion = "25.05";
  };
}

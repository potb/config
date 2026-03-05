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
        nh
        act
        ffmpeg
        lefthook
        _1password-cli
      ]
      ++ lib.optionals pkgs.stdenv.isLinux [
        gcc
        binutils
        libnotify
        lm_sensors
        audacity
        easyeffects
        prismlauncher
        vlc
        spotify
        slack
        discord
        jetbrains.datagrip
        bottles
      ]
      ++ lib.optionals pkgs.stdenv.isDarwin [
        stdenv.cc
      ];

    home.sessionVariables =
      {
        EDITOR = "nvim";
      }
      // lib.optionalAttrs pkgs.stdenv.isLinux {
        NH_FLAKE = "/home/potb/projects/potb/config";
        XDG_DATA_DIRS = "$HOME/Desktop:$XDG_DATA_DIRS";
      }
      // lib.optionalAttrs pkgs.stdenv.isDarwin {
        NH_FLAKE = lib.mkForce "/Users/potb/projects/potb/config";
        BROWSER = lib.mkForce "open -a 'Google Chrome'";
        CC = "${pkgs.stdenv.cc}/bin/cc";
        CXX = "${pkgs.stdenv.cc}/bin/c++";
      };

    home.stateVersion = "25.05";
  };
}

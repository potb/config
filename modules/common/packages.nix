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

    programs.jq.enable = true;

    home.packages = with pkgs; [
      fd
      fzf
      duf
      dust
      glow
      httpie
      bottom
      htop

      age
      croc
      lnav
      nmap
      rsync
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

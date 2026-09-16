{
  lib,
  pkgs,
  ...
}: {
  ghostty = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = let
        package =
          if pkgs.stdenv.hostPlatform.isDarwin
          then pkgs.ghostty-bin
          else pkgs.ghostty;
      in {
        available = package.meta.available or true;
        home.programs.ghostty.package = package;
      };

      homebrew-cask = {
        darwin.homebrew.casks = ["ghostty"];
        home.programs.ghostty.package = null;
      };
    };
  };

  google-chrome = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = let
        google-chrome = pkgs.google-chrome.override {
          commandLineArgs = [
            "--disable-gpu-memory-buffer-video-frames"
            "--disable-features=UseChromeOSDirectVideoDecoder"
            "--enable-features=VaapiVideoDecodeLinuxGL"
          ];
        };
      in {
        available = google-chrome.meta.available or true;
        home = {
          home.packages = [google-chrome];
          home.sessionVariables.AGENT_BROWSER_EXECUTABLE_PATH = "${google-chrome}/bin/google-chrome-stable";
        };
      };

      homebrew-cask = {
        darwin.homebrew.casks = ["google-chrome"];
        home.home.sessionVariables.AGENT_BROWSER_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
      };
    };
  };

  _1password-cli = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = {
        available = pkgs._1password-cli.meta.available or true;
        home.home.packages = [pkgs._1password-cli];
      };
      homebrew-cask.darwin.homebrew.casks = ["1password-cli"];
    };
  };

  slack = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = {
        available = pkgs.slack.meta.available or true;
        home.home.packages = [pkgs.slack];
      };
      homebrew-cask.darwin.homebrew.casks = ["slack"];
    };
  };

  spotify = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = {
        available = pkgs.spotify.meta.available or true;
        home.home.packages = [pkgs.spotify];
      };
      homebrew-cask.darwin.homebrew.casks = ["spotify"];
    };
  };

  discord = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = {
        available = pkgs.discord.meta.available or true;
        home.home.packages = [pkgs.discord];
      };
      homebrew-cask.darwin.homebrew.casks = ["discord"];
    };
  };

  qwerty-fr = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs = {
        available = pkgs.qwertyFr.meta.available or true;
        nixos = {
          environment.systemPackages = [pkgs.qwertyFr];
          environment.sessionVariables.XKB_CONFIG_EXTRA_PATH = "${pkgs.qwertyFr}/share/X11/xkb";
        };
      };

      homebrew-cask.darwin.homebrew.casks = ["qwerty-fr"];
    };
  };

  tailscale = {
    defaultChannel = {
      linux = "nixpkgs";
      darwin = "homebrew-cask";
    };

    channels = {
      nixpkgs.nixos = {
        services.tailscale = {
          enable = true;
          useRoutingFeatures = lib.mkDefault "none";
          openFirewall = true;
        };

        networking.firewall = {
          trustedInterfaces = ["tailscale0"];
          checkReversePath = "loose";
        };

        boot.kernel.sysctl = {
          "net.ipv4.conf.all.rp_filter" = 0;
          "net.ipv4.conf.default.rp_filter" = 0;
        };
      };

      homebrew-cask.darwin.homebrew = {
        casks = ["tailscale-app"];
        brews = ["tailscale"];
      };
    };
  };
}

{pkgs, ...}: let
  playwrightVars = {
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
  };
in {
  nixos = {
    hardware.graphics.extraPackages = with pkgs; [
      libva-vdpau-driver
      libvdpau-va-gl
    ];
  };

  home = {
    home.packages = [pkgs.agent-browser];

    linux = let
      google-chrome = pkgs.google-chrome.override {
        commandLineArgs = [
          "--disable-gpu-memory-buffer-video-frames"
          "--disable-features=UseChromeOSDirectVideoDecoder"
          "--enable-features=VaapiVideoDecodeLinuxGL"
        ];
      };
    in {
      home.sessionVariables =
        playwrightVars
        // {
          AGENT_BROWSER_EXECUTABLE_PATH = "${google-chrome}/bin/google-chrome-stable";
        };

      home.packages = [google-chrome];
    };

    darwin = {
      # Chrome comes from the Homebrew cask here, so point agent-browser at the
      # bundle rather than at a store path.
      home.sessionVariables =
        playwrightVars
        // {
          AGENT_BROWSER_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
        };
    };
  };
}

{
  pkgs,
  lib,
  ...
}: {
  nixos = {
    hardware.graphics.extraPackages = with pkgs; [
      libva-vdpau-driver
      libvdpau-va-gl
    ];
  };

  darwin = {};

  home = lib.optionalAttrs pkgs.stdenv.isLinux (
    let
      google-chrome = pkgs.google-chrome.override {
        commandLineArgs = [
          "--disable-gpu-memory-buffer-video-frames"
          "--disable-features=UseChromeOSDirectVideoDecoder"
          "--enable-features=VaapiVideoDecodeLinuxGL"
        ];
      };
    in {
      home.sessionVariables = {
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
        PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
        AGENT_BROWSER_EXECUTABLE_PATH = "${google-chrome}/bin/google-chrome-stable";
      };

      home.packages = [
        google-chrome
      ];
    }
  );
}

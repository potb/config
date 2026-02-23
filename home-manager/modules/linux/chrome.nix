{pkgs, ...}: let
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

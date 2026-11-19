{pkgs, ...}: {
  packages = ["google-chrome"];

  nixos = {
    hardware.graphics.extraPackages = with pkgs; [
      libva-vdpau-driver
      libvdpau-va-gl
    ];

    systemd.tmpfiles.rules = [
      "e /tmp/com.google.Chrome.* - - - 1d"
      "e /tmp/.org.chromium.Chromium.* - - - 1d"
      "e /tmp/scoped_dir* - - - 1d"
    ];
  };

  darwin = {};

  home = {
    home.packages = [pkgs.agent-browser];

    home.sessionVariables = {
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
      PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
    };
  };
}

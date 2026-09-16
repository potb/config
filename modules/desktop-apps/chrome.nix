{pkgs, ...}: {
  packages = ["google-chrome"];

  nixos = {
    hardware.graphics.extraPackages = with pkgs; [
      libva-vdpau-driver
      libvdpau-va-gl
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

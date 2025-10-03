{
  pkgs,
  lib,
  ...
}: {
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.blacklistedKernelModules = [];
  boot.kernelParams = [];

  systemd.settings = {
    Manager = {
      RuntimeWatchdogSec = "10s";
      RebootWatchdogSec = "10min";
      DefaultTimeoutStopSec = "15s";
    };
  };
}

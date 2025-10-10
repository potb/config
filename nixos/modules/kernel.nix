{
  pkgs,
  lib,
  ...
}: {
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.blacklistedKernelModules = [];
  boot.kernelParams = [];

  boot.kernel.sysctl = {
    "fs.inotify.max_user_instances" = 1048576;
    "fs.inotify.max_user_watches" = 1048576;
    "fs.inotify.max_queued_events" = 65536;
  };

  systemd.settings = {
    Manager = {
      RuntimeWatchdogSec = "10s";
      RebootWatchdogSec = "10min";
      DefaultTimeoutStopSec = "15s";
    };
  };
}

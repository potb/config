{
  pkgs,
  lib,
  ...
}: {
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.blacklistedKernelModules = [];
  boot.kernelParams = [
    "amdgpu.modeset=1"
    "quiet"
    "udev.log_level=3"
    # Mitigate iwlwifi/RCU expedited-stall race (kernel.org bugzilla #217856):
    # CPU got wedged in a permanent RCU stall on 2026-07-04, correlated with
    # the iwlmvm module and an intel_idle deep C-state transition.
    "pcie=noaer"
    "intel_idle.max_cstate=1"
  ];

  boot.consoleLogLevel = 0;
  boot.initrd.verbose = false;

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

  # Match system timeout for user services (xdg-document-portal hangs 90s otherwise)
  systemd.user.settings.Manager = {
    DefaultTimeoutStopSec = "15s";
  };
}

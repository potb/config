{...}: {
  nixos = {
    security.pam.loginLimits = [
      {
        domain = "*";
        type = "soft";
        item = "nofile";
        value = "1048576";
      }
      {
        domain = "*";
        type = "hard";
        item = "nofile";
        value = "1048576";
      }
    ];

    boot.kernel.sysctl = {
      "fs.inotify.max_user_instances" = 1048576;
      "fs.inotify.max_user_watches" = 1048576;
      "fs.inotify.max_queued_events" = 65536;
    };

    systemd.settings.Manager.DefaultTimeoutStopSec = "15s";
    systemd.user.settings.Manager.DefaultTimeoutStopSec = "15s";
  };

  darwin = {};
  home = {};
}

{...}: {
  systemd.settings.Manager = {
    RuntimeWatchdogSec = "10s";
    RebootWatchdogSec = "10min";
  };
}

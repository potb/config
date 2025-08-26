{
  pkgs,
  lib,
  ...
}: {
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.blacklistedKernelModules = ["iTCO_wdt"];
  boot.kernelParams = ["reboot=efi,force"];

  systemd.settings = {
    Manager = {
      RuntimeWatchdogSec = "0";
      ShutdownWatchdogSec = "0";
    };
  };
}

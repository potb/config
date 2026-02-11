{pkgs, ...}: let
  brightnessScript = pkgs.writeShellScript "monitor-brightness" ''
    set -euo pipefail

    DDCUTIL="${pkgs.ddcutil}/bin/ddcutil"
    HOUR=$(${pkgs.coreutils}/bin/date +%H)

    if [ "$HOUR" -ge 20 ] || [ "$HOUR" -lt 8 ]; then
      BRIGHTNESS=0
    else
      BRIGHTNESS=100
    fi

    # Detect all monitors dynamically — no hardcoded bus numbers
    BUSES=$($DDCUTIL detect --brief 2>/dev/null | ${pkgs.gnugrep}/bin/grep -oP 'I2C bus:\s+/dev/i2c-\K[0-9]+' || true)

    if [ -z "$BUSES" ]; then
      echo "No monitors detected via DDC/CI"
      exit 0
    fi

    for BUS in $BUSES; do
      echo "Setting bus $BUS brightness to $BRIGHTNESS"
      $DDCUTIL --bus "$BUS" setvcp 10 "$BRIGHTNESS" --noverify || echo "Failed on bus $BUS, continuing..."
    done
  '';
in {
  environment.systemPackages = [pkgs.ddcutil];

  systemd.services.monitor-brightness = {
    description = "Adjust monitor brightness based on time of day";
    after = ["systemd-modules-load.service"];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = brightnessScript;
    };
  };

  systemd.timers.monitor-brightness-evening = {
    description = "Dim monitors at 20:00";
    wantedBy = ["timers.target"];
    timerConfig = {
      OnCalendar = "*-*-* 20:00:00";
      Persistent = true;
    };
  };

  systemd.timers.monitor-brightness-morning = {
    description = "Restore monitors at 08:00";
    wantedBy = ["timers.target"];
    timerConfig = {
      OnCalendar = "*-*-* 08:00:00";
      Persistent = true;
    };
  };

  # Both timers trigger the same time-aware service
  systemd.timers.monitor-brightness-evening.unitConfig.Requires = "monitor-brightness.service";
  systemd.timers.monitor-brightness-morning.unitConfig.Requires = "monitor-brightness.service";

  # Also run on boot to catch up if booted between 20:00-08:00
  systemd.timers.monitor-brightness-boot = {
    description = "Set monitor brightness on boot";
    wantedBy = ["timers.target"];
    timerConfig = {
      OnBootSec = "1min";
    };
  };
  systemd.timers.monitor-brightness-boot.unitConfig.Requires = "monitor-brightness.service";
}

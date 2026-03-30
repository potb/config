{
  pkgs,
  config,
  ...
}: let
  absFloat = x:
    if x >= 0
    then x
    else 0 - x;

  # Manual fallback coordinates from config.location
  fallbackLat = toString (absFloat config.location.latitude);
  fallbackLatDir =
    if config.location.latitude >= 0
    then "N"
    else "S";
  fallbackLon = toString (absFloat config.location.longitude);
  fallbackLonDir =
    if config.location.longitude >= 0
    then "E"
    else "W";

  locationCache = "/run/monitor-brightness-location";

  brightnessScript = pkgs.writeShellScript "monitor-brightness" ''
    set -euo pipefail

    DDCUTIL="${pkgs.ddcutil}/bin/ddcutil"
    SUNWAIT="${pkgs.sunwait}/bin/sunwait"
    JQ="${pkgs.jq}/bin/jq"
    CURL="${pkgs.curl}/bin/curl"
    CACHE="${locationCache}"

    # --- Resolve coordinates ---
    # Try: 1) fresh IP geolocation  2) cached location  3) manual fallback
    resolve_location() {
      # Attempt IP geolocation (cache for 12h)
      if [ ! -f "$CACHE" ] || [ "$(${pkgs.findutils}/bin/find "$CACHE" -mmin +720 2>/dev/null)" ]; then
        RESPONSE=$($CURL -s --max-time 5 "http://ip-api.com/json?fields=status,lat,lon" 2>/dev/null || true)
        if echo "$RESPONSE" | $JQ -e '.status == "success"' >/dev/null 2>&1; then
          echo "$RESPONSE" > "$CACHE"
          echo "Location updated from IP geolocation" >&2
        fi
      fi

      # Read from cache
      if [ -f "$CACHE" ] && $JQ -e '.lat and .lon' "$CACHE" >/dev/null 2>&1; then
        RAW_LAT=$($JQ -r '.lat' "$CACHE")
        RAW_LON=$($JQ -r '.lon' "$CACHE")

        # Convert to sunwait format: absolute value + N/S/E/W
        LAT=$(echo "$RAW_LAT" | ${pkgs.coreutils}/bin/tr -d '-')
        LON=$(echo "$RAW_LON" | ${pkgs.coreutils}/bin/tr -d '-')
        LAT_DIR=$(echo "$RAW_LAT" | ${pkgs.gnugrep}/bin/grep -q '^-' && echo "S" || echo "N")
        LON_DIR=$(echo "$RAW_LON" | ${pkgs.gnugrep}/bin/grep -q '^-' && echo "W" || echo "E")
        echo "''${LAT}''${LAT_DIR} ''${LON}''${LON_DIR}"
        return
      fi

      # Fallback to compile-time config.location
      echo "Using manual fallback coordinates" >&2
      echo "${fallbackLat}${fallbackLatDir} ${fallbackLon}${fallbackLonDir}"
    }

    COORDS=$(resolve_location)
    echo "Using coordinates: $COORDS"

    # --- Determine day/night ---
    # sunwait poll civil: exit 2 = day, exit 3 = night
    set +e
    $SUNWAIT poll civil $COORDS
    SUN_STATE=$?
    set -e

    if [ "$SUN_STATE" -eq 2 ]; then
      BRIGHTNESS=100
    elif [ "$SUN_STATE" -eq 3 ]; then
      BRIGHTNESS=10
    else
      echo "sunwait returned unexpected code: $SUN_STATE"
      exit 1
    fi

    # --- Apply to all monitors ---
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
  environment.systemPackages = [
    pkgs.ddcutil
    pkgs.sunwait
  ];

  systemd.services.monitor-brightness = {
    description = "Adjust monitor brightness based on civil twilight";
    after = [
      "systemd-modules-load.service"
      "network-online.target"
    ];
    wants = ["network-online.target"];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = brightnessScript;
    };
  };

  # Single polling timer — every 15 minutes + on boot.
  # Location is fetched via IP geolocation, cached 12h, with manual fallback.
  systemd.timers.monitor-brightness = {
    description = "Poll and adjust monitor brightness";
    wantedBy = ["timers.target"];
    timerConfig = {
      OnBootSec = "1min";
      OnCalendar = "*:0/15";
      Persistent = true;
      Unit = "monitor-brightness.service";
    };
  };
}

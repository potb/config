{pkgs, ...}: let
  brightnessStep = pkgs.writeShellScript "brightness-step" ''
    set -euo pipefail
    DDCUTIL="${pkgs.ddcutil}/bin/ddcutil"
    STEP=10

    BUSES=$($DDCUTIL detect --brief 2>/dev/null | ${pkgs.gnugrep}/bin/grep -oP 'I2C bus:\s+/dev/i2c-\K[0-9]+' || true)
    [ -z "$BUSES" ] && exit 0

    FIRST_BUS=$(echo "$BUSES" | head -1)
    CURRENT=$($DDCUTIL --bus "$FIRST_BUS" getvcp 10 2>/dev/null | ${pkgs.gnugrep}/bin/grep -oP 'current value =\s*\K[0-9]+' || echo "50")

    case "''${1:-}" in
      up)   NEW=$(( CURRENT + STEP > 100 ? 100 : CURRENT + STEP )) ;;
      down) NEW=$(( CURRENT - STEP < 0   ? 0   : CURRENT - STEP )) ;;
      *)    exit 1 ;;
    esac

    for BUS in $BUSES; do
      $DDCUTIL --bus "$BUS" setvcp 10 "$NEW" --noverify &
    done
    wait
  '';
in {
  home.linux = {
    wayland.windowManager.hyprland.settings.bindl = [
      ", XF86MonBrightnessUp, exec, ${brightnessStep} up"
      ", XF86MonBrightnessDown, exec, ${brightnessStep} down"
    ];
  };
}

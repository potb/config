{
  config,
  pkgs,
  lib,
  ...
}: let
  tailscale = lib.getExe config.services.tailscale.package;

  serve = pkgs.writeShellScript "tailscale-serve-setup" ''
    set -euo pipefail

    ${tailscale} serve reset

    ${tailscale} serve --bg --https 443 http://127.0.0.1:18789
    ${tailscale} serve --bg --https 8443 http://127.0.0.1:8080
    ${tailscale} serve --bg --tcp 52100 tcp://127.0.0.1:52100

    ${tailscale} serve status
  '';
in {
  nixos = {
    systemd.services.tailscale-serve = {
      description = "Expose the gateway and browser on the tailnet over HTTPS";
      wantedBy = ["multi-user.target"];
      after = [
        "tailscaled.service"
        "tailscaled-autoconnect.service"
        "openclaw-gateway.service"
      ];
      wants = ["tailscaled.service"];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = serve;
        ExecStop = "${tailscale} serve reset";
        Restart = "on-failure";
        RestartSec = 30;
      };

      unitConfig = {
        StartLimitIntervalSec = 600;
        StartLimitBurst = 10;
      };
    };
  };

  darwin = {};
  home = {};
}

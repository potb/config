{
  config,
  pkgs,
  lib,
  ...
}: let
  serveConfig = {
    TCP = {
      "443" = {HTTPS = true;};
      "8443" = {HTTPS = true;};
    };
    Web = {
      "\${TS_CERT_DOMAIN}:443".Handlers."/" = {
        Proxy = "http://127.0.0.1:18789";
      };
      "\${TS_CERT_DOMAIN}:8443".Handlers."/" = {
        Proxy = "http://127.0.0.1:8080";
      };
    };
    AllowFunnel = {
      "\${TS_CERT_DOMAIN}:443" = false;
      "\${TS_CERT_DOMAIN}:8443" = false;
    };
  };

  serveConfigFile =
    (pkgs.formats.json {}).generate "tailscale-serve.json" serveConfig;
in {
  nixos = {
    systemd.services.tailscale-serve = {
      description = "Expose the gateway and browser on the tailnet over HTTPS";
      wantedBy = ["multi-user.target"];
      after = [
        "tailscaled.service"
        "tailscaled-autoconnect.service"
      ];
      wants = ["tailscaled.service"];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${lib.getExe config.services.tailscale.package} serve --config ${serveConfigFile}";
        ExecStop = "${lib.getExe config.services.tailscale.package} serve reset";
        Restart = "on-failure";
        RestartSec = 10;
      };
    };
  };

  darwin = {};
  home = {};
}

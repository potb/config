{
  lib,
  pkgs,
  ...
}: {
  networking.hostName = "charon";
  networking.networkmanager.enable = true;
  networking.networkmanager.dns = "none";
  networking.nameservers = ["127.0.0.1"];

  environment.systemPackages = [pkgs.cloudflared];

  systemd.services.cloudflared-doh = {
    description = "Cloudflared DoH";
    after = ["network-online.target"];
    wants = ["network-online.target"];
    wantedBy = ["multi-user.target"];
    serviceConfig = {
      ExecStart = "${pkgs.cloudflared}/bin/cloudflared proxy-dns --address 127.0.0.1 --port 53 --upstream https://1.1.1.1/dns-query --upstream https://1.0.0.1/dns-query";
      Restart = "always";
      RestartSec = 2;
    };
  };

  users.users.potb.extraGroups = lib.mkAfter ["networkmanager"];
}

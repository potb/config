{
  lib,
  inputs,
  ...
}: {
  networking.hostName = "kerberos";

  networking.networkmanager = {
    enable = true;
    wifi.backend = "iwd";
    dns = "none";
  };

  networking.wireless.iwd = {
    enable = true;
    settings.General.EnableNetworkConfiguration = false;
  };

  networking.nameservers = ["127.0.0.1"];
  networking.firewall.allowedTCPPorts = [4096];

  services.dnscrypt-proxy = {
    enable = true;
    settings = {
      listen_addresses = ["127.0.0.1:53"];
      server_names = ["cloudflare"];
      ipv6_servers = false;
      require_dnssec = true;
      cache = true;
      cache_size = 4096;
      sources.public-resolvers = {
        urls = [];
        cache_file = "${inputs.dnscrypt-resolvers}/v3/public-resolvers.md";
        minisign_key = "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3";
      };
    };
  };

  users.users.potb.extraGroups = lib.mkAfter ["networkmanager"];
}

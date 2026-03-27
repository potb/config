{
  lib,
  pkgs,
  inputs,
  ...
}: {
  networking.hostName = "charon";
  networking.networkmanager.enable = true;
  networking.networkmanager.dns = "none";
  networking.nameservers = ["127.0.0.1"];
  networking.firewall.allowedTCPPorts = [4096];

  # CNVi WiFi on Z790 can fail PCI enumeration at boot.
  # This service rescans PCI, loads iwlwifi, and restarts NetworkManager if no WiFi interface is found.
  systemd.services.wifi-pci-rescan = {
    description = "Rescan PCI bus for late-initializing CNVi WiFi";
    wantedBy = ["multi-user.target"];
    after = [
      "systemd-modules-load.service"
      "systemd-udev-settle.service"
    ];
    before = ["NetworkManager.service"];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = pkgs.writeShellScript "wifi-pci-rescan" ''
        # If a WiFi interface already exists, nothing to do
        if ${pkgs.iw}/bin/iw dev 2>/dev/null | grep -q Interface; then
          echo "WiFi interface found, skipping PCI rescan"
          exit 0
        fi

        echo "No WiFi interface detected — rescanning PCI bus"
        echo 1 > /sys/bus/pci/rescan
        sleep 2

        # Load iwlwifi in case it didn't autobind
        ${pkgs.kmod}/bin/modprobe iwlwifi 2>/dev/null || true
        sleep 1

        if ${pkgs.iw}/bin/iw dev 2>/dev/null | grep -q Interface; then
          echo "WiFi interface appeared after PCI rescan"
        else
          echo "WiFi interface still missing after PCI rescan"
        fi
      '';
    };
  };

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

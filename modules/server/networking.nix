{...}: {
  nixos = {
    networking.nftables.enable = true;

    networking.firewall = {
      enable = true;
      allowedTCPPorts = [];
      allowedUDPPorts = [];
      trustedInterfaces = ["tailscale0"];
      checkReversePath = "loose";
      allowPing = true;
      logRefusedConnections = false;
    };

    services.tailscale = {
      enable = true;
      useRoutingFeatures = "none";
      openFirewall = true;
    };

    systemd.services.tailscaled = {
      after = ["sops-nix.service"];
      wants = ["sops-nix.service"];
    };

    boot.kernel.sysctl = {
      "net.ipv4.conf.all.rp_filter" = 0;
      "net.ipv4.conf.default.rp_filter" = 0;
    };
  };

  darwin = {};
  home = {};
}

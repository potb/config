{...}: {
  nixos = {
    networking.nftables.enable = true;

    networking.firewall = {
      enable = true;
      allowedTCPPorts = [];
      allowedUDPPorts = [];
      allowPing = true;
      logRefusedConnections = false;
    };
  };

  darwin = {};
  home = {};
}

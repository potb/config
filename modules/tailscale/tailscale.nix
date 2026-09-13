{
  config,
  lib,
  ...
}: {
  nixos = {
    services.tailscale = {
      enable = true;
      useRoutingFeatures = "none";
      openFirewall = true;
    };

    networking.firewall = {
      trustedInterfaces = ["tailscale0"];
      checkReversePath = "loose";
    };

    boot.kernel.sysctl = {
      "net.ipv4.conf.all.rp_filter" = 0;
      "net.ipv4.conf.default.rp_filter" = 0;
    };

    systemd.services.tailscaled =
      lib.mkIf (config.services.tailscale.authKeyFile != null)
      {
        after = ["sops-nix.service"];
        wants = ["sops-nix.service"];
      };
  };

  darwin = {};
  home = {};
}

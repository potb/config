{
  config,
  lib,
  pkgs,
  ...
}: let
  # Reply traffic for connections that arrived from the internet is marked so a
  # policy route sends it back out the physical link. Without this the default
  # route the exit node installs swallows the replies and every public service,
  # SSH included, goes dark the moment an exit node is selected.
  #
  # The mark is our own rather than Tailscale's bypass mark, so the two never
  # have to agree on a bit pattern.
  mark = "0x1";
  rulePriority = 5000; # Ahead of Tailscale's own rule at 5270.
in {
  nixos = {
    networking.nftables.tables.exit-node-bypass =
      lib.mkIf config.networking.nftables.enable
      {
        family = "inet";
        content = ''
          chain prerouting {
            type filter hook prerouting priority mangle; policy accept;
            iifname != "${config.services.tailscale.interfaceName}" ct state new ct mark set ${mark}
          }

          chain output {
            type route hook output priority mangle; policy accept;
            ct mark ${mark} meta mark set ${mark}
          }
        '';
      };

    systemd.services.exit-node-bypass-rule = {
      description = "Route replies to inbound connections around the exit node";
      wantedBy = ["multi-user.target"];
      after = ["network.target"];

      path = with pkgs; [iproute2];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };

      script = ''
        for family in -4 -6; do
          ip $family rule del fwmark ${mark} lookup main priority ${toString rulePriority} 2>/dev/null || true
          ip $family rule add fwmark ${mark} lookup main priority ${toString rulePriority}
        done
      '';

      preStop = ''
        for family in -4 -6; do
          ip $family rule del fwmark ${mark} lookup main priority ${toString rulePriority} 2>/dev/null || true
        done
      '';
    };
  };

  darwin = {};
  home = {};
}

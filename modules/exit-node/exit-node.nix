{lib, ...}: {
  nixos = {
    # Offers this machine as an exit node. Forwarding comes from
    # `useRoutingFeatures = "server"`; the advertisement itself is a client
    # preference, re-applied by the tailscaled-set unit on every activation so
    # it survives a re-login or a state wipe.
    services.tailscale = {
      useRoutingFeatures = lib.mkForce "server";
      extraSetFlags = ["--advertise-exit-node"];
    };
  };

  darwin = {};
  home = {};
}

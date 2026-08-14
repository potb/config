{lib, ...}: let
  # Link-local and RFC1918 ranges only: sshd answers on the LAN (or a phone
  # tether, which hands out 172.20.10.0/24) and never on a routable source
  # address, even if this host later sits behind a port-forwarding router.
  localNetworks = [
    "10.0.0.0/8"
    "172.16.0.0/12"
    "192.168.0.0/16"
    "169.254.0.0/16"
  ];

  localNetworks6 = [
    "fc00::/7"
    "fe80::/10"
  ];

  # Written against the iptables firewall backend, which is what this host
  # uses. networking.nftables.enable would turn extraCommands into a build-time
  # assertion failure, so a backend switch fails loudly rather than silently
  # dropping the allowance; port these to firewall.extraInputRules if it flips.
  rule = bin: op: net: "${bin} -w ${op} nixos-fw -p tcp -s ${net} --dport 22 -j nixos-fw-accept";

  addRules =
    map (rule "iptables" "-A") localNetworks
    ++ map (rule "ip6tables" "-A") localNetworks6;

  delRules =
    map (net: "${rule "iptables" "-D" net} || true") localNetworks
    ++ map (net: "${rule "ip6tables" "-D" net} || true") localNetworks6;
in {
  nixos = {
    services.openssh = {
      enable = true;

      # No blanket port opening: the rules below scope port 22 to local sources.
      openFirewall = false;

      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "no";
        X11Forwarding = false;

        # Reverse lookups stall connection setup while the local resolver is
        # dnscrypt-proxy talking to an off-LAN upstream.
        UseDns = false;

        AllowUsers = ["potb"];

        # Long Rust and Nix builds outlive an idle NAT window on a tethered
        # link; keep the channel alive instead of dropping the job.
        ClientAliveInterval = 60;
        ClientAliveCountMax = 10;
      };
    };

    # Announce charon.local so clients need not chase a DHCP-assigned address.
    # mDNS is link-local by protocol, so openFirewall here is not remote reach.
    services.avahi = {
      enable = true;
      nssmdns4 = true;
      openFirewall = true;
      publish = {
        enable = true;
        addresses = true;
        workstation = true;
      };
    };

    networking.firewall = {
      extraCommands = lib.concatStringsSep "\n" addRules;
      extraStopCommands = lib.concatStringsSep "\n" delRules;
    };

    users.users.potb.openssh.authorizedKeys.keys = [
      # Peios-MacBook-Pro-2, ~/.ssh/id_ed25519. Not a host this flake manages,
      # so the key is recorded here rather than derived from a darwin config.
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPxwWHxRGidoXjaK6smBfBbHRdNfkLmumxEEN6bJpeD2 potb@Peios-MacBook-Pro-2"
    ];
  };

  darwin = {};

  home = {};
}

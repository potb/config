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
  # Neither machine can read the other's public key at evaluation time, so the
  # two are recorded here and each host authorises the other.
  charonKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPEvgHXpApOdOWFe5bKuZW4M3adoAvcDqFCaP7bYPkDu potb@charon";
  nyxKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDBNj+8QbPM+G7odRtOWOWZ/A+UQ6FvnYMnurBgXWXfk potb@nyx";
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

    users.users.potb.openssh.authorizedKeys.keys = [nyxKey];
  };

  darwin = {
    # Remote Login, so reaching nyx does not depend on someone having clicked
    # the Sharing panel. macOS keeps its own sshd_config; this appends to it.
    services.openssh.enable = true;

    users.users.potb.openssh.authorizedKeys.keys = [charonKey];
  };

  home = {
    programs.ssh = {
      enable = true;

      # Home Manager's own defaults for Host * are on their way out; keep the
      # ones worth having explicitly rather than inheriting a moving target.
      enableDefaultConfig = false;

      settings."*" = {
        AddKeysToAgent = "no";
        Compression = false;
        ForwardAgent = false;
        HashKnownHosts = false;
        ServerAliveInterval = 0;
        ServerAliveCountMax = 3;
        UserKnownHostsFile = "~/.ssh/known_hosts";
        ControlMaster = "no";
        ControlPath = "~/.ssh/master-%r@%n:%p";
        ControlPersist = "no";
      };

      settings."github.com" = {
        HostName = "github.com";
        User = "git";
        IdentitiesOnly = true;
      };
    };

    linux = {
      programs.ssh.settings = {
        nyx = {
          HostName = "Peios-MacBook-Pro-2.local";
          User = "potb";
          IdentityFile = "~/.ssh/id_ed25519";
        };

        "github.com".IdentityFile = "~/.ssh/id_ed25519";
      };
    };

    darwin = {
      programs.ssh.settings = {
        charon = {
          HostName = "charon.local";
          User = "potb";
          IdentityFile = "~/.ssh/id_ed25519_nyx";
        };

        "github.com".IdentityFile = "~/.ssh/id_ed25519_nyx";
      };
    };
  };
}

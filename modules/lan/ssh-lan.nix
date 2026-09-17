{lib, ...}: let
  keys = import ../../shared/keys.nix;

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

  rule = bin: op: net: "${bin} -w ${op} nixos-fw -p tcp -s ${net} --dport 22 -j nixos-fw-accept";

  addRules =
    map (rule "iptables" "-A") localNetworks
    ++ map (rule "ip6tables" "-A") localNetworks6;

  delRules =
    map (net: "${rule "iptables" "-D" net} || true") localNetworks
    ++ map (net: "${rule "ip6tables" "-D" net} || true") localNetworks6;
in {
  nixos = {
    services.openssh.openFirewall = false;

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

    users.users.potb.openssh.authorizedKeys.keys = [keys.nyx];
  };

  darwin = {
    users.users.potb.openssh.authorizedKeys.keys = [keys.charon];
  };

  home = {
    linux = {
      programs.ssh.settings = {
        nyx = {
          HostName = "nyx.local";
          User = "potb";
          IdentityFile = "~/.ssh/id_ed25519";
        };
      };
    };

    darwin = {
      programs.ssh.settings = {
        charon = {
          HostName = "charon.local";
          User = "potb";
          IdentityFile = "~/.ssh/id_ed25519_nyx";
        };
      };
    };
  };
}

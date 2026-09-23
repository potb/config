{lib, ...}: let
  keys = import ../../shared/keys.nix;
in {
  nixos = {
    services.openssh = {
      openFirewall = true;

      settings = {
        AllowTcpForwarding = "local";
        MaxAuthTries = 3;
      };
    };

    services.fail2ban = {
      enable = true;
      maxretry = 4;
      bantime = "1h";
      bantime-increment = {
        enable = true;
        maxtime = "168h";
      };
      ignoreIP = [
        "100.64.0.0/10"
        "127.0.0.1/8"
      ];
    };

    users.users.potb.openssh.authorizedKeys.keys = [keys.nyx keys.charon];
    users.users.root.openssh.authorizedKeys.keys = lib.mkForce [];
  };

  darwin = {};
  home = {};
}

{lib, ...}: let
  nyxKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDBNj+8QbPM+G7odRtOWOWZ/A+UQ6FvnYMnurBgXWXfk potb@nyx";
in {
  nixos = {
    services.openssh = {
      enable = true;
      openFirewall = true;

      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "no";
        X11Forwarding = false;
        AllowTcpForwarding = "local";
        AllowUsers = ["potb"];
        UseDns = false;
        MaxAuthTries = 3;
        ClientAliveInterval = 60;
        ClientAliveCountMax = 10;
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

    users.users.potb.openssh.authorizedKeys.keys = [nyxKey];
    users.users.root.openssh.authorizedKeys.keys = lib.mkForce [];

    security.sudo.wheelNeedsPassword = false;
  };

  darwin = {};
  home = {};
}

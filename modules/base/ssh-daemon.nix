{...}: {
  nixos = {
    services.openssh = {
      enable = true;

      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "no";
        X11Forwarding = false;

        UseDns = false;

        AllowUsers = ["potb"];

        ClientAliveInterval = 60;
        ClientAliveCountMax = 10;
      };
    };
  };

  darwin = {
    services.openssh.enable = true;
  };

  home = {
    programs.ssh = {
      enable = true;

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
      programs.ssh.settings."github.com".IdentityFile = "~/.ssh/id_ed25519";
    };

    darwin = {
      programs.ssh.settings."github.com".IdentityFile = "~/.ssh/id_ed25519_nyx";
    };
  };
}

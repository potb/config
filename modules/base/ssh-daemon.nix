{...}: let
  keys = import ../../shared/keys.nix;
  onePasswordAgent = "\"~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock\"";
in {
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
    services.openssh.enable = false;
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

    darwin = {osConfig, ...}: let
      host = osConfig.networking.hostName;
      publicKey = ".ssh/id_ed25519_${host}.pub";
    in {
      home.file.${publicKey}.text = keys.${host} + "\n";

      programs.ssh.settings = {
        "*" = {
          IdentityAgent = onePasswordAgent;
          IdentityFile = "~/${publicKey}";
          IdentitiesOnly = true;
        };

        "gitlab.com" = {
          HostName = "gitlab.com";
          User = "git";
        };
      };
    };
  };
}

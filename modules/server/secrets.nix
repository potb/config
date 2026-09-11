{config, ...}: let
  workspace = "/var/lib/openclaw/workspace";

  bootstrapFiles = [
    "SOUL.md"
    "AGENTS.md"
    "USER.md"
    "TOOLS.md"
  ];

  mkBootstrapSecret = name: {
    name = "workspace/${name}";
    value = {
      sopsFile = ../../secrets/workspace + "/${name}";
      format = "binary";
      path = "${workspace}/${name}";
      owner = "openclaw";
      group = "openclaw";
      mode = "0440";
      restartUnits = ["openclaw-gateway.service"];
    };
  };
in {
  nixos = {
    sops = {
      defaultSopsFile = ../../secrets/new-horizons.yaml;
      age.sshKeyPaths = ["/etc/ssh/ssh_host_ed25519_key"];

      secrets =
        {
          tailscale-authkey = {};

          openclaw-env = {
            owner = "openclaw";
            group = "openclaw";
            mode = "0400";
            restartUnits = ["openclaw-gateway.service"];
          };

          neko-env = {
            mode = "0400";
            restartUnits = ["podman-neko.service"];
          };

          restic-password = {mode = "0400";};
        }
        // builtins.listToAttrs (map mkBootstrapSecret bootstrapFiles);
    };

    services.tailscale.authKeyFile = config.sops.secrets.tailscale-authkey.path;
    services.tailscale.authKeyParameters.ephemeral = false;
  };

  darwin = {};
  home = {};
}

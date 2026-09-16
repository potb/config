{
  config,
  lib,
  ...
}: {
  packages = ["tailscale"];

  nixos = {
    systemd.services.tailscaled =
      lib.mkIf (config.services.tailscale.authKeyFile != null)
      {
        after = ["sops-nix.service"];
        wants = ["sops-nix.service"];
      };
  };

  darwin = {};
  home = {};
}

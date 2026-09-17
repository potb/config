{
  config,
  lib,
  ...
}: {
  nixos = {
    users.mutableUsers =
      lib.mkIf (config.users.users.potb.hashedPasswordFile != null)
      (lib.mkForce false);

    users.users.root.hashedPassword = lib.mkForce "!";

    security.sudo.wheelNeedsPassword = false;
  };

  darwin = {};
  home = {};
}

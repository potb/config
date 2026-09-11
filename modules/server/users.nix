{
  config,
  lib,
  ...
}: {
  nixos = {
    users.mutableUsers = lib.mkForce false;

    users.users.potb.hashedPasswordFile =
      config.sops.secrets.potb-password-hash.path;

    users.users.root.hashedPassword = lib.mkForce "!";

    security.sudo.wheelNeedsPassword = false;
  };

  darwin = {};
  home = {};
}

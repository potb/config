{lib, ...}: let
  keys = import ../../shared/keys.nix;
in {
  system.stateVersion = "24.11";

  users.users.potb.openssh.authorizedKeys.keys = [keys.new-horizons];

  nix.settings = {
    max-jobs = 4;
    cores = 8;
  };
}

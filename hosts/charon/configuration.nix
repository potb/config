{lib, ...}: {
  system.stateVersion = "24.11";

  nix.settings = {
    max-jobs = 4;
    cores = 8;
  };
}

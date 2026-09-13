{lib, ...}: {
  system.stateVersion = "24.11";

  nix.settings = {
    max-jobs = 2;
    cores = 4;
  };

  nixpkgs.hostPlatform = lib.mkDefault "aarch64-linux";
}

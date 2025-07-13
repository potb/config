{lib, ...}: {
  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  fileSystems."/".fsType = "ext4";
  fileSystems."/".device = "/dev/null";

  system.stateVersion = "24.11";
}

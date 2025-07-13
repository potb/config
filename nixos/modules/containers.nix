{lib, ...}: {
  boot.binfmt.emulatedSystems = ["aarch64-linux"];

  virtualisation.docker.enable = true;
  users.users.potb.extraGroups = lib.mkAfter ["docker"];
}

{lib, ...}: {
  networking.hostName = "charon";
  networking.networkmanager.enable = true;
  networking.nameservers = ["1.1.1.1"];

  users.users.potb.extraGroups = lib.mkAfter ["networkmanager"];
}

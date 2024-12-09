{
  lib,
  inputs,
  ...
}: {
  imports = with inputs; [lanzaboote.nixosModules.lanzaboote];

  boot.loader.systemd-boot.enable = lib.mkForce false;

  boot.lanzaboote = {
    enable = true;
    pkiBundle = "/etc/secureboot";
  };
  boot.loader.efi.canTouchEfiVariables = true;
}

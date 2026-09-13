{lib, ...}: {
  boot.loader.systemd-boot.enable = lib.mkForce true;
  boot.tmp.cleanOnBoot = true;
}

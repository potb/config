{
  pkgs,
  lib,
  ...
}: {
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.initrd.postDeviceCommands = lib.mkAfter ''
    mount -o subvol=@root /dev/vg0/root /mnt
    btrfs subvolume delete /mnt/@root
    btrfs subvolume snapshot /mnt/@root-blank /mnt/@root
    umount /mnt
  '';
}

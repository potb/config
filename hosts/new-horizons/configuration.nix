{lib, ...}: {
  nixpkgs.hostPlatform = "x86_64-linux";

  boot.loader.grub = {
    enable = true;
    device = "/dev/vda";
    efiSupport = false;
  };

  boot.initrd.availableKernelModules = [
    "virtio_pci"
    "virtio_blk"
    "virtio_scsi"
    "virtio_net"
    "ahci"
    "sd_mod"
    "sr_mod"
  ];
  boot.kernelModules = ["kvm-intel"];

  boot.tmp.cleanOnBoot = true;

  networking.useDHCP = lib.mkDefault true;

  time.timeZone = "Europe/Paris";
  i18n.defaultLocale = "en_US.UTF-8";

  documentation.nixos.enable = false;

  services.xserver.enable = false;
  services.printing.enable = false;

  system.stateVersion = "26.05";
}

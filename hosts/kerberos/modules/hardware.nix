{
  lib,
  pkgs,
  modulesPath,
  ...
}: let
  vendorFirmware = pkgs.runCommand "asahi-vendorfw" {} ''
    mkdir -p $out
    cp ${builtins.fetchurl {
      url = "file:///boot/vendorfw/firmware.cpio";
      sha256 = "b13a4b0027f9e80e9439511b76baf856792dee899da77e0726c579542ba8b489";
    }} $out/firmware.cpio
  '';
in {
  imports = [(modulesPath + "/installer/scan/not-detected.nix")];

  fileSystems."/" = {
    device = "/dev/disk/by-uuid/b939a6f5-97f7-4358-8856-3fe2f2e26175";
    fsType = "ext4";
  };

  fileSystems."/boot" = {
    device = "/dev/disk/by-uuid/42DE-1DF2";
    fsType = "vfat";
    options = [
      "fmask=0022"
      "dmask=0022"
    ];
  };

  hardware.asahi.enable = true;
  hardware.asahi.peripheralFirmwareDirectory = vendorFirmware;

  hardware.bluetooth = {
    enable = true;
    powerOnBoot = true;
    settings = {
      Policy.AutoEnable = true;
      General = {
        FastConnectable = true;
        JustWorksRepairing = "always";
      };
    };
  };

  services.gvfs.enable = true;
  services.udisks2.enable = true;
  services.fwupd.enable = true;

  networking.useDHCP = lib.mkDefault false;
}

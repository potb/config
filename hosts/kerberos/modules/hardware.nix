{
  lib,
  modulesPath,
  ...
}: {
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

{
  config,
  lib,
  modulesPath,
  ...
}: {
  imports = [(modulesPath + "/installer/scan/not-detected.nix")];

  fileSystems."/" = lib.mkForce {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
  };

  fileSystems."/boot" = lib.mkForce {
    device = "/dev/disk/by-label/boot";
    fsType = "vfat";
    options = [
      "fmask=0077"
      "dmask=0077"
    ];
  };

  boot.initrd.availableKernelModules = [
    "vmd"
    "xhci_pci"
    "ahci"
    "nvme"
    "usbhid"
    "usb_storage"
    "sd_mod"
  ];
  boot.initrd.kernelModules = ["amdgpu"];
  boot.kernelModules = [
    "kvm-intel"
    "nct6775"
  ];
  boot.kernelParams = ["acpi_enforce_resources=lax"];
  boot.extraModulePackages = [];
  boot.supportedFilesystems = ["ntfs"];

  hardware.graphics = {
    enable = true;
    enable32Bit = true;
  };
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;
  hardware.bluetooth.settings = {
    Policy = {
      AutoEnable = true;
    };
    General = {
      FastConnectable = true;
      JustWorksRepairing = "always";
    };
  };
  hardware.keyboard.zsa.enable = true;
  hardware.i2c.enable = true;

  services.xserver.videoDrivers = ["amdgpu"];
  services.gvfs.enable = true;
  services.udisks2.enable = true;
  services.pcscd.enable = true;

  systemd.services.amdgpu-perf-fix = {
    description = "Set AMD GPU to high performance mode";
    wantedBy = ["multi-user.target"];
    after = ["systemd-modules-load.service"];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "/run/current-system/sw/bin/bash -c 'echo high > /sys/class/drm/card1/device/power_dpm_force_performance_level'";
      RemainAfterExit = true;
    };
  };

  networking.useDHCP = lib.mkDefault true;

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.intel.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}

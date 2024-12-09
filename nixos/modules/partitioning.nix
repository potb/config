{inputs, ...}: {
  imports = with inputs; [disko.nixosModules.disko];

  disko.devices = {
    disk = {
      one = {
        type = "disk";
        device = "/dev/nvme0n1";
        content = {
          type = "gpt";
          partitions = {
            boot = {
              size = "4G";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
                mountOptions = ["defaults"];
              };
            };
            windows = {
              size = "912G";
              type = "0700";
              content = {
                type = "filesystem";
                format = "ntfs";
                extraArgs = ["--fast"];
              };
            };
            install = {
              size = "8G";
              type = "0700";
              content = {
                type = "filesystem";
                format = "ntfs";
                extraArgs = ["--fast"];
              };
            };
            linux = {
              size = "912G";
              type = "8300";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
                mountOptions = ["defaults"];
              };
            };
            swap = {
              size = "24G";
              type = "8200";
              content = {
                type = "swap";
              };
            };
          };
        };
      };
    };
  };
}

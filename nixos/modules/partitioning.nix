{inputs, ...}: {
  imports = with inputs; [disko.nixosModules.disko];

  disko.devices = {
    disk = {
      nvme0n1 = {
        type = "disk";
        device = "/dev/nvme0n1";
        content = {
          type = "gpt";
          partitions = {
            boot = {
              size = "1G";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
              };
            };
            lvm = {
              size = "100%";
              content = {
                type = "lvm_pv";
                vg = "vg0";
              };
            };
          };
        };
      };
    };

    lvm_vg = {
      vg0 = {
        type = "lvm_vg";
        lvs = {
          root = {
            size = "20%FREE";
            content = {
              type = "btrfs";
              subvolumes = {
                "@root" = {
                  mountpoint = "/";
                  mountOptions = [
                    "compress=zstd"
                    "noatime"
                  ];
                };
                "@root-blank" = {
                  readonly = true;
                };
              };
            };
          };
          nix = {
            size = "25%FREE";
            content = {
              type = "filesystem";
              format = "ext4";
              mountpoint = "/nix";
              neededForBoot = true;
            };
          };
          home = {
            size = "50%FREE";
            content = {
              type = "filesystem";
              format = "ext4";
              mountpoint = "/home";
            };
          };
          swap = {
            size = "64G";
            content = {
              type = "swap";
            };
          };
        };
      };
    };
  };
}

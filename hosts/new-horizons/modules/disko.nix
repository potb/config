{lib, ...}: {
  disko.devices = lib.mkForce {
    disk = {
      main = {
        type = "disk";
        device = "/dev/vda";
        content = {
          type = "gpt";
          partitions = {
            biosboot = {
              label = "biosboot";
              size = "1M";
              type = "EF02";
              priority = 1;
            };
            swap = {
              label = "swap";
              size = "4G";
              content = {
                type = "swap";
                discardPolicy = "once";
              };
            };
            root = {
              label = "nixos";
              size = "100%";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
                extraArgs = ["-L" "nixos"];
              };
            };
          };
        };
      };
    };
  };
}

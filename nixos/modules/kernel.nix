{
  pkgs,
  lib,
  ...
}: {
  boot.kernelPackages = pkgs.linuxPackages_latest;
  # boot.kernelParams = [ "amdgpu.dcdebugmask=0x10" ];
}

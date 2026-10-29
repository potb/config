{pkgs, ...}: {
  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
    extraCompatPackages = with pkgs; [
      proton-ge-bin
    ];
  };

  programs.gamemode.enable = true;

  environment.systemPackages = with pkgs; [
    tsm-app

    mangohud
    amdgpu_top
    nvtopPackages.amd
    sysstat
    file
    protontricks
  ];
}

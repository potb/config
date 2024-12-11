{pkgs, lib, ...}: {
  # Hardware settings
  hardware.graphics = {
    enable = true;
    enable32Bit = true;
  };
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;
  hardware.keyboard.zsa.enable = true;

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  fileSystems."/".fsType = "ext4";
  fileSystems."/".device = "/dev/null";


  services.xserver.videoDrivers = ["amdgpu"];
  services.gvfs.enable = true;
  services.udisks2.enable = true;
  services.pcscd.enable = true;

  # User settings
  users.users.potb = {
    isNormalUser = true;
    description = "Peïo Thibault";
    extraGroups = [
      "wheel"
    ];
    shell = pkgs.zsh;
  };

  services.displayManager = {
    autoLogin.enable = true;
    autoLogin.user = "potb";
    defaultSession = "none+i3";
  };

  # X server settings
  services.xserver.enable = true;
  services.xserver.excludePackages = [pkgs.xterm];
  services.xserver.desktopManager.xterm.enable = false;
  services.xserver = {
    windowManager.i3 = {
      enable = true;
      package = pkgs.i3-gaps;
      extraPackages = with pkgs; [
        dmenu
        i3status
      ];
    };

    displayManager = {
      lightdm = {
        enable = true;
        greeter.enable = false;
      };
    };

    xkb = {
      layout = "qwerty-fr";

      extraLayouts."qwerty-fr" = let
        qwerty-fr = pkgs.qwerty-fr;
      in {
        description = qwerty-fr.meta.description;
        languages = ["eng"];
        symbolsFile = "${qwerty-fr}/share/X11/xkb/symbols/us_qwerty-fr";
      };
    };
  };

  # Program settings
  programs.zsh.enable = true;
  programs.nix-ld.enable = true;
  # Services
  services.gnome.gnome-keyring.enable = true;

  # System packages
  environment.systemPackages = with pkgs; [discord];

  # Kernel packages
  boot.kernelPackages = pkgs.linuxPackages_latest;

  # Nixpkgs settings
  nixpkgs.config.allowUnfree = true;

  # Documentation settings
  documentation.nixos.enable = false;

  # System state version
  system.stateVersion = "24.11";
}

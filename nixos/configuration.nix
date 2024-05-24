{
  inputs,
  config,
  pkgs,
  lib,
  ...
}: {
  imports = [
    ./hardware-configuration.nix
    ./disko.nix
  ];

  # Nix settings
  nix = let
    flakeInputs = lib.filterAttrs (_: lib.isType "flake") inputs;
  in {
    settings = {
      experimental-features = "nix-command flakes";
      warn-dirty = false;
      auto-optimise-store = true;
      trusted-users = ["root" "@wheel"];
      flake-registry = "";
      nix-path = config.nix.nixPath;
    };

    channel.enable = false;

    registry = lib.mapAttrs (_: flake: {inherit flake;}) flakeInputs;
    nixPath = lib.mapAttrsToList (n: _: "${n}=flake:${n}") flakeInputs;

    gc = {
      automatic = true;
      dates = "daily";
      options = "--delete-older-than 7d";
    };
  };

  # Global theme
  catppuccin = {
    enable = true;
    flavor = "latte";
  };

  # Boot settings
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Hardware settings
  hardware.opengl = {
    enable = true;
    driSupport32Bit = true;
  };
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;
  hardware.keyboard.zsa.enable = true;

  services.xserver.videoDrivers = ["amdgpu"];
  services.gvfs.enable = true;
  services.udisks2.enable = true;
  services.fwupd.enable = true;

  # Time and localization settings
  time.timeZone = "Europe/Paris";
  time.hardwareClockInLocalTime = true;

  i18n.defaultLocale = "en_US.UTF-8";
  i18n.extraLocaleSettings = {
    LC_ADDRESS = "en_US.UTF-8";
    LC_IDENTIFICATION = "en_US.UTF-8";
    LC_MEASUREMENT = "en_US.UTF-8";
    LC_MONETARY = "en_US.UTF-8";
    LC_NAME = "en_US.UTF-8";
    LC_NUMERIC = "en_US.UTF-8";
    LC_PAPER = "en_US.UTF-8";
    LC_TELEPHONE = "en_US.UTF-8";
    LC_TIME = "en_US.UTF-8";
  };

  # Network settings
  networking.hostName = "charon";
  networking.networkmanager.enable = true;

  # Virtualization settings
  virtualisation.docker.enable = true;
  virtualisation.libvirtd.enable = true;
  virtualisation.libvirtd.qemu = {
    package = pkgs.qemu_kvm;
    runAsRoot = true;
  };
  virtualisation.spiceUSBRedirection.enable = true;

  # Sound settings
  hardware.pulseaudio.enable = false;
  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;

    extraConfig.pipewire = {
      "01-buffer-underrun" = {
        link.max-buffers = 64;
      };
    };
  };

  # User settings
  users.users.potb = {
    isNormalUser = true;
    description = "Peïo Thibault";
    extraGroups = ["networkmanager" "wheel" "docker" "libvirtd"];
    shell = pkgs.zsh;
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
      defaultSession = "none+i3";

      lightdm = {
        enable = true;
        greeter.enable = false;
        autoLogin.enable = true;
        autoLogin.user = "potb";
      };
    };

    xkb = {
      layout = "qwerty-fr";

      extraLayouts."qwerty-fr" = let
        qwerty-fr = pkgs.callPackage ./qwerty-fr.nix {};
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

  systemd.services.update-apod-wallpaper = {
    description = "Update APOD Wallpaper";
    script = let
      curl = "${pkgs.curl}/bin/curl";
      feh = "${pkgs.feh}/bin/feh";
      file = "${pkgs.file}/bin/file";
    in ''
      set -eu

      IMAGE_DIR="$HOME/Pictures/apod"
      IMAGE_PATH="$IMAGE_DIR/apod.jpg"
      TEMP_IMAGE_PATH="$IMAGE_DIR/apod_temp.jpg"
      APOD_URL="https://apod.nasa.gov/apod/astropix.html"

      export DISPLAY=:0

      mkdir -p $IMAGE_DIR

      IMAGE_URL=$(${curl} -s $APOD_URL | grep -oP '(?<=<a href="image/).*?(?=")' | head -n 1 || echo "")
      if [ -z "$IMAGE_URL" ]; then
        echo "No image found on APOD page."
        exit 1
      fi

      IMAGE_URL="https://apod.nasa.gov/apod/image/$IMAGE_URL"

      ${curl} -s $IMAGE_URL -o $TEMP_IMAGE_PATH

      if ${file} $TEMP_IMAGE_PATH | grep -qE 'image|bitmap'; then
        mv $TEMP_IMAGE_PATH $IMAGE_PATH
        ${feh} --bg-max $IMAGE_PATH
      else
        echo "Downloaded file is not a valid image. Keeping the old wallpaper."
        rm $TEMP_IMAGE_PATH
      fi
    '';
    serviceConfig = {
      Type = "oneshot";
      User = "potb";
      Environment = "DISPLAY=:0";
    };
    wantedBy = ["multi-user.target"];
  };

  systemd.timers.update-apod-wallpaper = {
    wantedBy = ["timers.target"];
    timerConfig = {
      OnCalendar = "0/6:00:00"; # Run every 6 hours
      Persistent = true;
      Unit = "update-apod-wallpaper.service";
    };
  };

  # System packages
  environment.systemPackages = with pkgs; [
    (poetry.override {python3 = python311Full;})
    python311Full
    quickemu
    discord
    sbctl
  ];

  # Stylix settings
  stylix = let
    theme = "${pkgs.base16-schemes}/share/themes/catppuccin-latte.yaml";
    wallpaper = pkgs.runCommand "image.png" {} ''
      COLOR=$(${pkgs.yq}/bin/yq -r .palette.base00 ${theme})
      COLOR="#"$COLOR
      ${pkgs.imagemagick}/bin/magick convert -size 2540x1460 xc:$COLOR $out
    '';
  in {
    image = wallpaper;
    base16Scheme = theme;
  };

  # Kernel packages
  boot.kernelPackages = pkgs.linuxPackages_latest;

  # Nixpkgs settings
  nixpkgs.config.allowUnfree = true;

  # Documentation settings
  documentation.nixos.enable = false;

  # System state version
  system.stateVersion = "24.05"; # Did you read the comment?
}

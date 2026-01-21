{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../shared/fonts.nix {inherit pkgs;};
in {
  nixpkgs.hostPlatform = lib.mkDefault "aarch64-darwin";

  networking.hostName = "nyx";

  # Fonts (managed at system level on Darwin, not home-manager)
  fonts.packages = [
    fonts.monospace.package
    fonts.ui.package
  ];

  security.pam.services.sudo_local.touchIdAuth = true;

  system.defaults = {
    NSGlobalDomain = {
      ApplePressAndHoldEnabled = false;
      InitialKeyRepeat = 15;
      KeyRepeat = 2;
      "com.apple.keyboard.fnState" = true;
    };
    finder = {
      AppleShowAllFiles = true;
    };
    dock = {
      show-recents = false;
      tilesize = 40;
    };
    CustomUserPreferences = {
      "com.apple.HIToolbox" = {
        AppleFnUsageType = 0;
        AppleDictationAutoEnable = false;
      };
    };
  };

  system.stateVersion = 5;
}

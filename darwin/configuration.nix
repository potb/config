{lib, ...}: {
  nixpkgs.hostPlatform = lib.mkDefault "aarch64-darwin";

  networking.hostName = "nyx";

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

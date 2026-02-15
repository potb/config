{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../shared/fonts.nix {inherit pkgs;};
in {
  nixpkgs.hostPlatform = lib.mkDefault "aarch64-darwin";

  networking.hostName = "nyx";

  fonts.packages = [
    fonts.monospace.package
    fonts.ui.package
  ];

  security.pam.services.sudo_local.touchIdAuth = true;

  system.defaults = {
    NSGlobalDomain = {
      # Keyboard settings (KEEP EXISTING - custom qwerty-fr layout)
      ApplePressAndHoldEnabled = false;
      InitialKeyRepeat = 15;
      KeyRepeat = 2;
      "com.apple.keyboard.fnState" = true;

      # File extensions and UI
      AppleShowAllExtensions = true;
      AppleShowScrollBars = "WhenScrolling";

      # Text input and autocorrect
      NSAutomaticCapitalizationEnabled = false;
      NSAutomaticDashSubstitutionEnabled = false;
      NSAutomaticPeriodSubstitutionEnabled = false;
      NSAutomaticQuoteSubstitutionEnabled = false;
      NSAutomaticSpellingCorrectionEnabled = false;

      # Document and dialog behavior
      NSDocumentSaveNewDocumentsToCloud = false;
      NSNavPanelExpandedStateForSaveMode = true;
      NSNavPanelExpandedStateForSaveMode2 = true;
      PMPrintingExpandedStateForPrint = true;
      PMPrintingExpandedStateForPrint2 = true;

      # Menu bar
      _HIHideMenuBar = false;
    };
    finder = {
      AppleShowAllFiles = true;
      AppleShowAllExtensions = true;
      FXPreferredViewStyle = "clmv";
      FXDefaultSearchScope = "SCcf";
      FXEnableExtensionChangeWarning = false;
      ShowPathbar = true;
      ShowStatusBar = true;
      _FXShowPosixPathInTitle = true;
      _FXSortFoldersFirst = true;
    };
    dock = {
      show-recents = false;
      tilesize = 40;
      autohide = true;
      autohide-delay = 0.0;
      autohide-time-modifier = 0.2;
      minimize-to-application = true;
      mru-spaces = false;
      orientation = "bottom";
      show-process-indicators = true;
      static-only = false;
      launchanim = false;
    };
    trackpad = {
      Clicking = true;
      TrackpadRightClick = true;
      TrackpadThreeFingerDrag = false;
    };
    spaces = {
      spans-displays = false;
    };
    screencapture = {
      location = "~/Pictures/Screenshots";
      type = "png";
      "disable-shadow" = true;
    };
    loginwindow = {
      GuestEnabled = false;
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

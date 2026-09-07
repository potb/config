{
  pkgs,
  lib,
  ...
}: let
  fonts = import ../shared/fonts.nix {inherit pkgs;};
in {
  nixpkgs.hostPlatform = lib.mkDefault "aarch64-darwin";

  networking = {
    hostName = "nyx";

    # scutil keeps three names. Bonjour advertises the local one, so charon
    # reaches this machine at nyx.local once activation renames it.
    localHostName = "nyx";
    computerName = "nyx";

    # Matches charon: incoming connections are refused unless something is
    # listening for them on purpose, and signed software is exempt.
    applicationFirewall = {
      enable = true;
      allowSigned = true;
      allowSignedApp = true;
      enableStealthMode = true;
      blockAllIncoming = false;
    };
  };

  # Remote builds and `darwin-rebuild switch` over SSH outlive the ten minute
  # idle timer this machine shipped with. The display may still sleep.
  power.sleep = {
    computer = "never";
    harddisk = "never";
    display = 10;
  };

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
    hitoolbox.AppleFnUsageType = "Do Nothing";

    controlcenter = {
      BatteryShowPercentage = true;
      Bluetooth = true;
      Sound = true;
    };

    menuExtraClock = {
      Show24Hour = true;
      ShowDate = 1;
      ShowDayOfWeek = true;
      ShowSeconds = false;
    };

    # Nix writes application bundles to the store, and the quarantine flag on
    # them produces an "are you sure" dialog for software this configuration
    # installed on purpose.
    LaunchServices.LSQuarantine = false;

    screensaver = {
      askForPassword = true;
      askForPasswordDelay = 5;
    };

    CustomUserPreferences = {
      "com.apple.HIToolbox".AppleDictationAutoEnable = false;
    };
  };

  system.stateVersion = 5;
}

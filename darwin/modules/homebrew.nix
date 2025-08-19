{...}: {
  homebrew = {
    enable = true;
    onActivation = {
      autoUpdate = true;
      cleanup = "zap";
      upgrade = true;
    };

    # Common GUI applications that are better installed via Homebrew on macOS
    casks = [
      "spotify"
      "google-chrome"
      "slack"
      "discord"
      "jetbrains-toolbox"
    ];

    # Mac App Store applications
    masApps = {
      # Add any Mac App Store apps here if needed
    };
  };
}
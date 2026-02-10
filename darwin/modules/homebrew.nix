{config, ...}: {
  homebrew = {
    enable = true;
    taps = builtins.attrNames config.nix-homebrew.taps;
    onActivation = {
      cleanup = "zap";
      autoUpdate = false;
      upgrade = false;
    };
    casks = [
      "discord"
      "google-chrome"
      "raycast"
      "slack"
      "spotify"
      "datagrip"
    ];
  };
}

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
      "1password"
      "discord"
      "google-chrome"
      "raycast"
      "slack"
      "spotify"
      "datagrip"
      "claude"
      "google-drive"
      "granola"
      "linear-linear"
    ];
  };
}

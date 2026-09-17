{
  config,
  lib,
  ...
}: {
  environment.systemPath = lib.mkAfter ["/opt/homebrew/bin"];

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
      "aldente"
      "claude"
      "claude-code"
      "google-drive"
      "granola"
      "karabiner-elements"
      "linear"
      "linearmouse"
      "notion"
      "raycast"
      "temurin"
      "zed"
    ];

    brews = [
      "jaisonerick/tap/macwifi-cli"
      "potb/tap/alloydb-auth-proxy"

      "precomp"
      "wallpaper"
    ];
  };
}

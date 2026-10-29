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
      "granola"
      "karabiner-elements"
      "linear"
      "linearmouse"
      "raycast"
      "temurin"
    ];

    brews = [
      "potb/tap/alloydb-auth-proxy"
    ];
  };
}

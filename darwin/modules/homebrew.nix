{config, ...}: {
  homebrew = {
    enable = true;
    taps = builtins.attrNames config.nix-homebrew.taps;
    onActivation = {
      # nyx carried ~190 formulae and 23 casks from its pre-Nix life. The
      # command-line ones now come from nixpkgs, but "zap" would delete them
      # all in the same activation that installs their replacements, and
      # "check" would abort activation while any stray remains. Leave cleanup
      # off until the nixpkgs versions are confirmed working, then run
      # `brew bundle cleanup --file=$(nix eval --raw ...)` to review, and
      # finally switch this to "zap".
      cleanup = "none";
      autoUpdate = false;
      upgrade = false;
    };

    # GUI applications stay with Homebrew even when nixpkgs has them. Nix
    # installs .app bundles into /Applications/Nix Apps, and nix-darwin's
    # App Management check aborts activation over SSH unless the Mac grants
    # full disk access to remote logins. Casks avoid that failure mode and
    # keep the vendors' own auto-updaters working.
    casks = [
      "1password"
      "1password-cli"
      "aerospace"
      "aldente"
      "claude"
      "claude-code"
      "datagrip"
      "discord"
      "ghostty"
      "gcloud-cli"
      "google-chrome"
      "google-drive"
      "granola"
      "hammerspoon"
      "linear"
      "linearmouse"
      "notion"
      "qwerty-fr"
      "raycast"
      "slack"
      "spotify"
      "tailscale-app"
      "temurin"
      "webstorm"
      "zed"

      "font-fira-code-nerd-font"
      "font-inter"
      "font-symbols-only-nerd-font"
    ];

    # Formulae with no nixpkgs equivalent.
    brews = [
      "borders"
      "precomp"
      "wallpaper"
    ];
  };
}

{config, ...}: {
  homebrew = {
    enable = true;
    taps = builtins.attrNames config.nix-homebrew.taps;
    onActivation = {
      # The command-line tools nyx carried from its pre-Nix life now come
      # from nixpkgs and resolve ahead of Homebrew's copies, so the originals
      # are dead weight. `brew bundle cleanup` reports 185 formulae and no
      # casks; every one of them either has a nixpkgs equivalent already
      # installed or was only ever a dependency of one that does.
      cleanup = "zap";
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

    # Formulae with no nixpkgs equivalent, or that provide a macOS service
    # this machine already runs from Homebrew's own launchd agents.
    brews = [
      "felixkratz/formulae/borders"
      "felixkratz/formulae/sketchybar"
      "asmvik/formulae/skhd"

      "jaisonerick/tap/macwifi-cli"
      "potb/tap/alloydb-auth-proxy"

      "precomp"
      "wallpaper"

      # The formula ships the CLI; the tailscale-app cask above carries the
      # network extension the CLI talks to, and only the app is signed for it.
      "tailscale"

      "hashicorp/tap/terraform"
    ];
  };
}
